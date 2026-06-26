--- Offline self-test for voicemode-media-keys.lua.
---
--- Hammerspoon is not available in CI and the real event tap needs macOS
--- Accessibility + physical key presses (a human-in-the-loop step — see
--- docs/reference/control-channel.md). This test instead stubs the `hs` API and
--- drives the *pure decision logic* — liveness, ownership resolution, and the
--- swallow-vs-pass-through verdict for every key × owner combination, plus the
--- side effects (which `voicemode control` commands fire).
---
--- Run with the same runtime Hammerspoon uses:
---     luajit scripts/hammerspoon/test_voicemode_media_keys.lua
--- (plain `lua` also works.)

-- ---------------------------------------------------------------------------
-- Test harness
-- ---------------------------------------------------------------------------

local passed, failed = 0, 0

local function check(cond, msg)
    if cond then
        passed = passed + 1
    else
        failed = failed + 1
        io.stderr:write("  FAIL: " .. msg .. "\n")
    end
end

local function eq(got, want, msg)
    check(got == want, string.format("%s (got %s, want %s)", msg, tostring(got), tostring(want)))
end

-- ---------------------------------------------------------------------------
-- `hs` stub
-- ---------------------------------------------------------------------------

local HOME = os.getenv("HOME") or "/tmp"
local SOCKET = HOME .. "/.voicemode/control.sock"

-- Mutable test state.
local stubState = {
    live = false,            -- is the control socket "bound"?
    controlCommands = {},    -- captured `voicemode control <cmd>` invocations
}

local function resetCaptured() stubState.controlCommands = {} end

hs = {
    fs = {
        attributes = function(path)
            if path == SOCKET then
                return stubState.live and { mode = "socket" } or nil
            end
            -- Pretend the configured voicemode binary exists so it resolves.
            if path == "/fake/bin/voicemode" then return { mode = "file" } end
            return nil
        end,
    },
    task = {
        new = function(_path, _cb, args)
            return {
                start = function()
                    -- args == { "control", "<command>" }
                    table.insert(stubState.controlCommands, args[2])
                end,
            }
        end,
    },
    eventtap = {
        event = { types = { systemDefined = "systemDefined" } },
        new = function(_types, _cb) return { start = function() end, stop = function() end } end,
    },
    hotkey = {
        bind = function(_mods, _key, _fn) return { delete = function() end } end,
    },
    menubar = {
        new = function()
            return {
                setTitle = function() end, setTooltip = function() end,
                setMenu = function() end, delete = function() end,
            }
        end,
    },
    alert = { show = function() end },
    execute = function() return "" end,
    printf = function() end,
}

-- ---------------------------------------------------------------------------
-- Load the module under test (config: deterministic path, no menubar/alerts)
-- ---------------------------------------------------------------------------

_G.voicemodeMediaKeys = {
    voicemodePath = "/fake/bin/voicemode",
    showMenubar = false,
    alertOnAction = false,
}

-- Resolve path to the module relative to this test file.
local thisDir = (arg[0] or ""):match("^(.*)[/\\]") or "."
local M = dofile(thisDir .. "/voicemode-media-keys.lua")

-- Build a fake NSSystemDefined event.
local function event(key, down, isRepeat)
    return {
        systemKey = function()
            return { key = key, down = down, ["repeat"] = isRepeat or false }
        end,
    }
end

local PRESS, RELEASE = true, false

-- ---------------------------------------------------------------------------
-- 1. Liveness signal tracks socket presence
-- ---------------------------------------------------------------------------

stubState.live = false
eq(M.isConverseLive(), false, "no socket -> not live")
stubState.live = true
eq(M.isConverseLive(), true, "socket present -> live")

-- ---------------------------------------------------------------------------
-- 2. Ownership resolution: override wins, else follow liveness
-- ---------------------------------------------------------------------------

M.ownership = "auto"
stubState.live = true;  eq(M._resolveOwner(), "voicemode", "auto + live -> voicemode")
stubState.live = false; eq(M._resolveOwner(), "music", "auto + dead -> music")

M.ownership = "always-me"
stubState.live = false; eq(M._resolveOwner(), "voicemode", "always-me overrides dead")
M.ownership = "always-music"
stubState.live = true;  eq(M._resolveOwner(), "music", "always-music overrides live")
M.ownership = "auto"

-- ---------------------------------------------------------------------------
-- 3. Non-media systemDefined keys always pass through (return false)
-- ---------------------------------------------------------------------------

stubState.live = true
eq(M._onSystemDefined(event("SOUND_UP", PRESS)), false, "volume key passes through")
eq(M._onSystemDefined(event("MUTE", PRESS)), false, "mute key passes through")

-- ---------------------------------------------------------------------------
-- 4. No converse live: every media key passes through (music owns)
-- ---------------------------------------------------------------------------

stubState.live = false
resetCaptured()
eq(M._onSystemDefined(event("NEXT", PRESS)), false, "dead: NEXT passes through")
eq(M._onSystemDefined(event("PREVIOUS", PRESS)), false, "dead: PREVIOUS passes through")
eq(M._onSystemDefined(event("PLAY", PRESS)), false, "dead: PLAY passes through")
eq(#stubState.controlCommands, 0, "dead: no control commands fired")

-- ---------------------------------------------------------------------------
-- 5. Converse live + Next = barge (swallow + `voicemode control stop`)
-- ---------------------------------------------------------------------------

stubState.live = true
resetCaptured()
eq(M._onSystemDefined(event("NEXT", PRESS)), true, "live: NEXT swallowed")
eq(#stubState.controlCommands, 1, "live: NEXT fires one command")
eq(stubState.controlCommands[1], "stop", "live: NEXT -> control stop (barge)")
-- The matching key-up is also swallowed but fires nothing.
resetCaptured()
eq(M._onSystemDefined(event("NEXT", RELEASE)), true, "live: NEXT release swallowed")
eq(#stubState.controlCommands, 0, "live: NEXT release fires nothing")
-- Auto-repeat is swallowed but does not re-fire.
resetCaptured()
eq(M._onSystemDefined(event("NEXT", PRESS, true)), true, "live: NEXT repeat swallowed")
eq(#stubState.controlCommands, 0, "live: NEXT repeat fires nothing")

-- ---------------------------------------------------------------------------
-- 6. Converse live + Previous = replay STUB (swallow, no control command)
-- ---------------------------------------------------------------------------

stubState.live = true
resetCaptured()
eq(M._onSystemDefined(event("PREVIOUS", PRESS)), true, "live: PREVIOUS swallowed")
eq(#stubState.controlCommands, 0, "live: PREVIOUS is a stub -> no control command (VM-1685)")

-- ---------------------------------------------------------------------------
-- 7. Play/Pause = do-both: always pass through, toggles VoiceMode when live
-- ---------------------------------------------------------------------------

stubState.live = true
resetCaptured()
-- First press while live -> pause; passes through.
eq(M._onSystemDefined(event("PLAY", PRESS)), false, "live: PLAY passes through (1)")
eq(stubState.controlCommands[1], "pause", "live: 1st PLAY -> pause")
-- Second press -> resume.
eq(M._onSystemDefined(event("PLAY", PRESS)), false, "live: PLAY passes through (2)")
eq(stubState.controlCommands[2], "resume", "live: 2nd PLAY -> resume")
-- Third press -> pause again (toggles back).
eq(M._onSystemDefined(event("PLAY", PRESS)), false, "live: PLAY passes through (3)")
eq(stubState.controlCommands[3], "pause", "live: 3rd PLAY -> pause")

-- Going not-live resets the toggle mirror: next live press pauses (not resumes).
eq(M._onSystemDefined(event("PLAY", PRESS)), false, "transition: PLAY passes through")  -- still live=true here
stubState.live = false
resetCaptured()
eq(M._onSystemDefined(event("PLAY", PRESS)), false, "dead: PLAY passes through")
eq(#stubState.controlCommands, 0, "dead: PLAY fires no control command")
stubState.live = true
resetCaptured()
eq(M._onSystemDefined(event("PLAY", PRESS)), false, "relive: PLAY passes through")
eq(stubState.controlCommands[1], "pause", "relive: first PLAY after dead -> pause (mirror reset)")

-- ---------------------------------------------------------------------------
-- 8. Manual override changes Next/Previous routing regardless of liveness
-- ---------------------------------------------------------------------------

-- always-music: even when live, Next passes through to music.
M.setOwnership("always-music")
stubState.live = true
resetCaptured()
eq(M._onSystemDefined(event("NEXT", PRESS)), false, "always-music: NEXT passes through despite live")
eq(#stubState.controlCommands, 0, "always-music: NEXT fires no control command")

-- always-me: even when dead, Next barges.
M.setOwnership("always-me")
stubState.live = false
resetCaptured()
eq(M._onSystemDefined(event("NEXT", PRESS)), true, "always-me: NEXT swallowed despite dead")
eq(stubState.controlCommands[1], "stop", "always-me: NEXT -> control stop despite dead")

-- cycleOwnership walks auto -> always-me -> always-music -> auto.
M.setOwnership("auto")
M.cycleOwnership(); eq(M.ownership, "always-me", "cycle: auto -> always-me")
M.cycleOwnership(); eq(M.ownership, "always-music", "cycle: always-me -> always-music")
M.cycleOwnership(); eq(M.ownership, "auto", "cycle: always-music -> auto")

-- ---------------------------------------------------------------------------
-- Report
-- ---------------------------------------------------------------------------

print(string.format("voicemode-media-keys self-test: %d passed, %d failed", passed, failed))
if failed > 0 then os.exit(1) end
