--- voicemode-media-keys.lua — bind the macOS media keys to VoiceMode's control channel.
---
--- VoiceMode (VM-1676) exposes a "control channel": a Unix-domain socket
--- (`~/.voicemode/control.sock`) bound by the running server *for the duration of
--- a converse turn*, driven by the `voicemode control pause|resume|stop` CLI. This
--- Hammerspoon config turns the keyboard's media keys (Logitech MX Keys Mini and
--- friends) into a control surface for that channel — WITHOUT permanently stealing
--- the keys from Spotify/Music.
---
--- Ownership model — "polite spot-instance" (VM-1724, Mike's decision 2026-06-27):
---   VoiceMode only grabs the media keys when a converse is *live*; otherwise every
---   key passes straight through to the active media app, unchanged.
---
---   • Play/Pause = "pause everything." One press quiets the room: it pauses
---     VoiceMode (if it is speaking) AND lets the event through so the media app
---     toggles too. Press again to resume. Coherent whether or not a converse is
---     live. (do-both / pass-through)
---   • Next / Previous route to the *active owner* (they can't be both — barge vs
---     music-skip conflict):
---       – converse live (or override=always-me) → VoiceMode owns:
---           Next = barge (`voicemode control stop`); Previous = replay (STUB,
---           pending VM-1685) — the event is swallowed so music never sees it.
---       – no converse (or override=always-music) → pass through to the media app
---           (normal next / previous track).
---   • Manual override toggle (auto / always-me / always-music) forces ownership
---     either direction regardless of converse state. Cycle it with the hotkey
---     below or the menubar item.
---
--- Liveness signal: the control socket is bound for the whole converse turn
--- (speaking AND listening — see voice_mode/tools/converse.py
--- `_control_listener_scope`), so the *presence* of `~/.voicemode/control.sock`
--- is the precise "is a converse live?" answer, and it is exactly the precondition
--- for a `voicemode control` command to land. We stat it synchronously on each key
--- event (cheap — no CLI spawn). The only false-positive is a socket left stale by
--- a server that crashed mid-utterance; it self-heals on the next converse, and the
--- worst case is a single Next/Previous that is swallowed and no-ops.
---
--- Requires macOS Accessibility permission for Hammerspoon (System Settings →
--- Privacy & Security → Accessibility). See docs/reference/control-channel.md.
---
--- Load from ~/.hammerspoon/init.lua:
---     local vmkeys = dofile(os.getenv("HOME") .. "/path/to/voicemode-media-keys.lua")
---   or, if this file is on the Lua path:
---     require("voicemode-media-keys")
---
--- Optional config before loading (all have sane defaults):
---     _G.voicemodeMediaKeys = {
---       voicemodePath  = "/custom/bin/voicemode",   -- else auto-resolved
---       socketPath     = "~/.voicemode/control.sock",
---       toggleHotkey   = { mods = {"cmd","alt","ctrl"}, key = "M" },
---       showMenubar    = true,
---       alertOnAction  = true,                      -- brief hs.alert on barge/pause
---       pauseEverything = false,                    -- Play/Pause scope when a converse
---                                                   -- is live (see below)
---     }
---
--- `pauseEverything` controls what Play/Pause does WHILE A CONVERSE IS LIVE:
---   • false (default) — pause/resume *only* VoiceMode; the key is swallowed so the
---     media app is left untouched (it won't start a paused track). Clean "pause me".
---   • true — the original "pause everything": also pass the key through so the media
---     app toggles too. One press quiets both, but a *paused* media source will
---     START (a stateless toggle can't know which way you meant).
--- When NO converse is live, Play/Pause always passes straight through to the media
--- app in both modes (VoiceMode never steals it during normal listening).

local M = {}

-- ---------------------------------------------------------------------------
-- Configuration & path resolution (resolved once, at load time)
-- ---------------------------------------------------------------------------

local userCfg = (type(_G.voicemodeMediaKeys) == "table") and _G.voicemodeMediaKeys or {}

local HOME = os.getenv("HOME") or ""

--- Expand a leading "~" to $HOME (Lua has no tilde expansion).
local function expanduser(p)
    if type(p) ~= "string" then return p end
    if p:sub(1, 1) == "~" then
        return HOME .. p:sub(2)
    end
    return p
end

--- True if a filesystem path exists (any type).
local function path_exists(p)
    return p ~= nil and p ~= "" and hs.fs.attributes(p) ~= nil
end

--- Resolve an absolute `voicemode` executable. Media-key handlers do NOT inherit
--- an interactive shell PATH, so we must hand `hs.task` an absolute path.
--- Order: explicit override → common install locations → a login-shell `command -v`.
local function resolve_voicemode_path()
    if userCfg.voicemodePath and path_exists(expanduser(userCfg.voicemodePath)) then
        return expanduser(userCfg.voicemodePath)
    end
    local candidates = {
        HOME .. "/.local/bin/voicemode",
        "/opt/homebrew/bin/voicemode",
        "/usr/local/bin/voicemode",
    }
    for _, p in ipairs(candidates) do
        if path_exists(p) then return p end
    end
    -- Last resort: ask the user's login shell (loads their profile/PATH).
    local out = hs.execute("command -v voicemode", true)
    if out then
        out = out:gsub("%s+$", "")
        if out ~= "" and path_exists(out) then return out end
    end
    return nil
end

local VOICEMODE_PATH = resolve_voicemode_path()

local SOCKET_PATH = expanduser(
    userCfg.socketPath
    or os.getenv("VOICEMODE_CONTROL_SOCKET")
    or "~/.voicemode/control.sock"
)

local ALERT_ON_ACTION = userCfg.alertOnAction ~= false  -- default true
local SHOW_MENUBAR = userCfg.showMenubar ~= false        -- default true
-- Play/Pause scope while a converse is live: default false = pause VoiceMode only
-- (swallow the key); true = do-both "pause everything" (also pass through to media).
local PAUSE_EVERYTHING = userCfg.pauseEverything == true

-- ---------------------------------------------------------------------------
-- State
-- ---------------------------------------------------------------------------

-- Manual ownership override: "auto" | "always-me" | "always-music".
M.ownership = "auto"

-- Local mirror of whether *we* last told VoiceMode to pause (drives the Play/Pause
-- toggle). Reset whenever no converse is live so each new turn starts un-paused;
-- any drift only ever costs one no-op pause/resume server-side.
local vmPaused = false

-- ---------------------------------------------------------------------------
-- Liveness
-- ---------------------------------------------------------------------------

--- Is a converse live right now? True iff the control socket is currently bound.
--- Synchronous single stat — safe to call inside the eventtap callback.
local function is_converse_live()
    local attrs = hs.fs.attributes(SOCKET_PATH)
    return attrs ~= nil and attrs.mode == "socket"
end
M.isConverseLive = is_converse_live

--- Who owns Next/Previous for this event? Override wins; else follow liveness.
local function resolve_owner()
    if M.ownership == "always-me" then return "voicemode" end
    if M.ownership == "always-music" then return "music" end
    return is_converse_live() and "voicemode" or "music"
end

-- ---------------------------------------------------------------------------
-- Shelling out to `voicemode control` (non-blocking)
-- ---------------------------------------------------------------------------

--- Fire a `voicemode control <command>` without blocking the event tap.
--- A failure (e.g. nothing listening) is logged at debug and otherwise ignored —
--- the control channel is a convenience, never load-bearing for the keypress.
local function voicemode_control(command)
    if not VOICEMODE_PATH then
        hs.printf("[voicemode-media-keys] voicemode not found on PATH; skipping `control %s`", command)
        return
    end
    local task = hs.task.new(VOICEMODE_PATH, function(exitCode, _stdout, stderr)
        if exitCode ~= 0 then
            -- Non-zero is normal when nothing is speaking (socket not bound).
            hs.printf("[voicemode-media-keys] `voicemode control %s` exit=%s %s",
                command, tostring(exitCode), (stderr or ""):gsub("%s+$", ""))
        end
    end, { "control", command })
    task:start()
end

local function alert(msg)
    if ALERT_ON_ACTION then hs.alert.show(msg, 0.8) end
end

-- ---------------------------------------------------------------------------
-- Key behaviours
-- ---------------------------------------------------------------------------

--- Play/Pause side effect: toggle VoiceMode pause/resume when a converse is live.
--- `live` is computed once by the caller, which also owns the swallow-vs-pass-through
--- decision (see on_system_defined / `pauseEverything`).
local function handle_play(live)
    if live then
        if vmPaused then
            voicemode_control("resume"); vmPaused = false
            alert("VoiceMode ▶ resume")
        else
            voicemode_control("pause"); vmPaused = true
            alert("VoiceMode ⏸ pause")
        end
    else
        -- Nothing speaking: keep the toggle mirror clean so the next live turn
        -- starts from "not paused". Music still toggles via pass-through.
        vmPaused = false
    end
end

--- Next, with VoiceMode owning → barge (cut the current utterance).
local function handle_next_voicemode()
    voicemode_control("stop")
    alert("VoiceMode ⏭ barge")
end

--- Previous, with VoiceMode owning → replay last utterance. STUB: there is no
--- `replay` control command yet — it is owned by VM-1685. Swallow the key and
--- tell the user, so it does not silently skip the music track. Swap the body for
--- `voicemode_control("replay")` (or similar) when VM-1685 lands.
local function handle_previous_voicemode()
    -- TODO(VM-1685): replace with the real replay/skip-back control command.
    hs.printf("[voicemode-media-keys] Previous: replay not yet available (VM-1685 stub)")
    hs.alert.show("VoiceMode ⏮ replay not yet available (VM-1685)", 1.2)
end

-- ---------------------------------------------------------------------------
-- The event tap
-- ---------------------------------------------------------------------------

--- Callback for every NSSystemDefined event. Returns `true` to swallow the event
--- (so the media app never sees it) or `false` to pass it through.
local function on_system_defined(event)
    local t = event:systemKey()
    if not t or not t.key then return false end

    local key = t.key
    -- Some keyboards (e.g. Logitech MX Keys Mini) report the next/previous-track
    -- keys as FAST/REWIND rather than NEXT/PREVIOUS (verified live, VM-1724).
    -- Normalise them so the routing below is hardware-independent.
    if key == "FAST" then
        key = "NEXT"
    elseif key == "REWIND" then
        key = "PREVIOUS"
    end
    if key ~= "PLAY" and key ~= "NEXT" and key ~= "PREVIOUS" then
        return false  -- volume / brightness / etc. — never ours
    end

    -- Act only on the press (down) edge, ignoring auto-repeat, so a held key
    -- fires the side effect once. `t.down == false` is the matching key-up.
    local isPressEdge = t.down and not t["repeat"]

    if key == "PLAY" then
        -- Toggle VoiceMode on the press edge. The swallow decision depends on mode:
        --   * live + default (pauseEverything=false): control ONLY VoiceMode and
        --     SWALLOW the key so the media app is untouched (no surprise un-pausing).
        --   * live + pauseEverything=true: also pass through -> "pause everything".
        --   * no converse live: always pass through (never steal it during listening).
        local live = is_converse_live()
        if isPressEdge then handle_play(live) end
        return live and not PAUSE_EVERYTHING
    end

    -- NEXT / PREVIOUS route to a single owner.
    if resolve_owner() == "music" then
        return false  -- pass the whole key (down/up/repeat) to the media app
    end

    -- VoiceMode owns: swallow the key entirely so music never skips, and fire the
    -- behaviour once on the press edge.
    if isPressEdge then
        if key == "NEXT" then
            handle_next_voicemode()
        else
            handle_previous_voicemode()
        end
    end
    return true
end

-- Exposed for the offline self-test (scripts/hammerspoon/test_voicemode_media_keys.lua),
-- which stubs `hs` and drives the decision logic without Hammerspoon.
M._resolveOwner = resolve_owner
M._onSystemDefined = on_system_defined

-- ---------------------------------------------------------------------------
-- Override toggle: hotkey + menubar
-- ---------------------------------------------------------------------------

local OWNERSHIP_NEXT = {
    ["auto"] = "always-me",
    ["always-me"] = "always-music",
    ["always-music"] = "auto",
}

local MENUBAR_TITLE = {
    ["auto"] = "VM⌨︎:auto",
    ["always-me"] = "VM⌨︎:me",
    ["always-music"] = "VM⌨︎:music",
}

local function refresh_menubar()
    if not M.menubar then return end
    M.menubar:setTitle(MENUBAR_TITLE[M.ownership] or "VM⌨︎")
    M.menubar:setTooltip("VoiceMode media-key ownership")
    M.menubar:setMenu({
        { title = "Media-key ownership", disabled = true },
        { title = "auto — follow converse", checked = M.ownership == "auto",
          fn = function() M.setOwnership("auto") end },
        { title = "always VoiceMode (always-me)", checked = M.ownership == "always-me",
          fn = function() M.setOwnership("always-me") end },
        { title = "always Music (always-music)", checked = M.ownership == "always-music",
          fn = function() M.setOwnership("always-music") end },
        { title = "-" },
        { title = "Converse live: " .. (is_converse_live() and "yes" or "no"), disabled = true },
        { title = "voicemode: " .. (VOICEMODE_PATH or "NOT FOUND"), disabled = true },
    })
end

--- Set the ownership mode and surface it (alert + menubar).
function M.setOwnership(mode)
    if not OWNERSHIP_NEXT[mode] then return end
    M.ownership = mode
    refresh_menubar()
    hs.alert.show("VoiceMode keys → " .. mode, 1.0)
end

--- Cycle auto → always-me → always-music → auto.
function M.cycleOwnership()
    M.setOwnership(OWNERSHIP_NEXT[M.ownership])
end

-- ---------------------------------------------------------------------------
-- Lifecycle
-- ---------------------------------------------------------------------------

--- Tear down a previous instance (idempotent — safe to call on reload).
function M.stop()
    if M.tap then M.tap:stop(); M.tap = nil end
    if M.hotkey then M.hotkey:delete(); M.hotkey = nil end
    if M.menubar then M.menubar:delete(); M.menubar = nil end
end

--- Start the event tap, the override hotkey, and the menubar.
function M.start()
    M.stop()  -- clean slate on reload

    M.tap = hs.eventtap.new({ hs.eventtap.event.types.systemDefined }, on_system_defined)
    M.tap:start()

    local hk = userCfg.toggleHotkey or { mods = { "cmd", "alt", "ctrl" }, key = "M" }
    M.hotkey = hs.hotkey.bind(hk.mods, hk.key, M.cycleOwnership)

    if SHOW_MENUBAR then
        M.menubar = hs.menubar.new()
        refresh_menubar()
    end

    if not VOICEMODE_PATH then
        hs.printf("[voicemode-media-keys] WARNING: `voicemode` not found — pass-through still works, "
            .. "but VoiceMode commands will be skipped. Set voicemodePath in _G.voicemodeMediaKeys.")
    end
    hs.printf("[voicemode-media-keys] started (ownership=%s, socket=%s, voicemode=%s)",
        M.ownership, SOCKET_PATH, VOICEMODE_PATH or "NOT FOUND")
    return M
end

-- Re-loading this file should not leak a previous tap/hotkey/menubar.
if _G.__voicemodeMediaKeys and _G.__voicemodeMediaKeys.stop then
    _G.__voicemodeMediaKeys.stop()
end
_G.__voicemodeMediaKeys = M

M.start()

return M
