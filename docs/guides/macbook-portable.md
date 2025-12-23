# Running VoiceMode with MacBook Lid Closed

This guide covers how to keep VoiceMode running on your MacBook when you close the lid - essential for portable voice conversations when you're on the go.

## The Problem

By default, macOS suspends your MacBook when you close the lid, which interrupts VoiceMode sessions. Apple's official "clamshell mode" requires an external display connected, but there are workarounds for headless operation.

## Quick Solution: pmset

The simplest solution uses the built-in `pmset` command:

```bash
# Before closing your lid - disable sleep
sudo pmset -a disablesleep 1

# When you're done - re-enable normal behavior
sudo pmset -a disablesleep 0
```

To verify the setting is active:

```bash
pmset -g assertions
```

!!! warning "Remember to Re-enable"
    Don't forget to run `sudo pmset -a disablesleep 0` when you're done, or your MacBook will never sleep even when you want it to.

## GUI Alternative: Amphetamine

For a more user-friendly approach, [Amphetamine](https://apps.apple.com/app/amphetamine/id937984704) is a free Mac App Store app with a "Closed-Display Mode" feature:

1. Install Amphetamine from the Mac App Store
2. Open Amphetamine preferences
3. Go to **Sessions → Non-Trigger Sessions**
4. Uncheck **"Allow system to sleep when display is closed"**
5. Start an Amphetamine session before closing your lid

## MacBook Air Thermal Considerations

If you're using a MacBook Air (M1, M2, M3, or M4), note that it's fanless and uses the keyboard area for cooling. Running with the lid closed limits heat dissipation.

**For VoiceMode use**: Audio processing is lightweight, so thermal throttling is unlikely. You should be fine for voice conversations.

**For intensive workloads**: Expect up to 50% performance reduction after extended closed-lid operation. Consider using a MacBook Pro for heavy workloads in clamshell mode.

## Using VoiceMode on the Go

### Recommended Workflow

1. **Before leaving**: Start your Claude Code session with VoiceMode
2. **Enable closed-lid mode**: `sudo pmset -a disablesleep 1`
3. **Close the lid and go**: Put your MacBook in your bag
4. **Converse**: Use your AirPods or headphones for voice interaction
5. **When done**: Re-enable sleep with `sudo pmset -a disablesleep 0`

### Tips for Backpack Operation

- **Bluetooth**: Ensure your audio device stays connected (Bluetooth remains active with `disablesleep`)
- **Battery**: Monitor battery usage - the Mac will drain faster than when sleeping
- **Ventilation**: Use a ventilated laptop sleeve if possible
- **Low Power Mode**: Enable Low Power Mode (System Settings → Battery) to extend battery life

### What About caffeinate?

The `caffeinate` command prevents idle sleep but does **not** prevent lid-close sleep. Use `pmset disablesleep` instead.

## Verifying VoiceMode Works

Test your setup before relying on it:

1. Enable closed-lid mode: `sudo pmset -a disablesleep 1`
2. Start a VoiceMode conversation
3. Close the lid while still talking
4. Confirm audio continues through your wireless headphones

## Troubleshooting

### Audio Stops When Lid Closes

- Verify `disablesleep` is enabled: `pmset -g | grep disablesleep`
- Check if another power assertion is overriding: `pmset -g assertions`
- Try the Amphetamine app as an alternative

### Bluetooth Audio Disconnects

- AirPods and some Bluetooth devices may auto-disconnect when they detect the Mac is "closing"
- Try reconnecting after closing the lid
- Consider wired audio for maximum reliability

### Mac Gets Hot in Bag

- Reduce workload (stick to audio-only tasks)
- Enable Low Power Mode
- Use a ventilated sleeve
- Take breaks to let it cool

## See Also

- [Configuration Guide](configuration.md) - VoiceMode settings
- [Selecting Voices](selecting-voices.md) - Voice configuration
- [Troubleshooting](../troubleshooting/index.md) - General VoiceMode issues
