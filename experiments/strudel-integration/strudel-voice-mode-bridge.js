#!/usr/bin/env node

/**
 * Strudel Voice Mode Bridge
 * 
 * This bridges Strudel's pattern generation with voice mode hooks.
 * Since audio playback requires Web Audio API, we have two options:
 * 1. Generate MIDI/OSC messages to an external synthesizer
 * 2. Use a headless browser (puppeteer) to run the full Strudel
 * 3. Generate pattern data that triggers local sound files
 */

import { sequence, stack, s, note, Pattern } from '@strudel/core';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

// Voice Mode Tool -> Strudel Sound Mapping
const TOOL_SOUNDS = {
    'bash': 'kick',
    'grep': 'hihat',
    'read': 'snare',
    'write': 'clap',
    'edit': 'cowbell',
    'multi_edit': 'cymbal',
    'task': 'tom',
    'web_fetch': 'rimshot',
    'web_search': 'shaker',
    'converse': 'bell'
};

// Pattern generator for voice mode events
class VoiceModeStrudel {
    constructor() {
        this.basePattern = null;
        this.currentCycle = 0;
        this.bpm = 120;
        this.isPlaying = false;
    }

    // Initialize with a base rhythmic pattern
    init(patternString = 'kick [~ hihat] snare hihat') {
        this.basePattern = s(patternString);
        console.log('Initialized base pattern:', patternString);
    }

    // Generate events for a specific time range
    getEvents(startTime, endTime) {
        if (!this.basePattern) return [];
        return this.basePattern.queryArc(startTime, endTime);
    }

    // Create a pattern from tool usage
    createToolPattern(toolSequence) {
        const sounds = toolSequence.map(tool => TOOL_SOUNDS[tool] || 'click');
        return s(sounds.join(' '));
    }

    // Quantize tool events to the beat
    quantizeToolEvent(toolName, beatPosition = null) {
        const sound = TOOL_SOUNDS[toolName] || 'click';
        
        // If no position specified, use next beat
        if (beatPosition === null) {
            beatPosition = Math.ceil(this.currentCycle * 4) / 4;
        }
        
        return {
            sound,
            time: beatPosition,
            tool: toolName
        };
    }

    // Play a sound using local audio (macOS example)
    async playSound(soundName) {
        // This could be replaced with actual sound file playback
        // For now, we'll use macOS 'say' command as a placeholder
        const soundMap = {
            'kick': 'boom',
            'hihat': 'tss',
            'snare': 'crack',
            'clap': 'clap',
            'cowbell': 'ding',
            'cymbal': 'crash',
            'tom': 'thud',
            'rimshot': 'tick',
            'shaker': 'shh',
            'bell': 'bing',
            'click': 'click'
        };
        
        const word = soundMap[soundName] || 'beep';
        
        try {
            // Use macOS say command for demo (replace with actual audio playback)
            await execAsync(`say -r 300 "${word}"`);
        } catch (error) {
            console.error(`Failed to play sound ${soundName}:`, error);
        }
    }

    // Simulate pattern playback
    async playPattern(duration = 4) {
        this.isPlaying = true;
        const events = this.getEvents(0, duration);
        
        console.log(`Playing ${events.length} events over ${duration} cycles...`);
        
        for (const event of events) {
            if (!this.isPlaying) break;
            
            const delayMs = event.whole.begin * (60000 / this.bpm);
            
            setTimeout(async () => {
                console.log(`Playing: ${event.value} at beat ${event.whole.begin}`);
                await this.playSound(event.value.value || event.value);
            }, delayMs);
        }
        
        // Wait for pattern to complete
        await new Promise(resolve => setTimeout(resolve, duration * (60000 / this.bpm)));
        this.isPlaying = false;
    }

    // Stop playback
    stop() {
        this.isPlaying = false;
    }
}

// Hook integration example
class VoiceModeHookIntegration {
    constructor() {
        this.strudel = new VoiceModeStrudel();
        this.toolHistory = [];
    }

    // Called when a voice mode tool is triggered
    async onToolTrigger(toolName) {
        console.log(`Tool triggered: ${toolName}`);
        
        // Add to history
        this.toolHistory.push(toolName);
        
        // Quantize and play the sound
        const event = this.strudel.quantizeToolEvent(toolName);
        await this.strudel.playSound(event.sound);
        
        // If we have enough events, create a pattern
        if (this.toolHistory.length >= 4) {
            const pattern = this.strudel.createToolPattern(this.toolHistory.slice(-4));
            console.log('Generated pattern from recent tools:', this.toolHistory.slice(-4));
        }
    }

    // Start background rhythm
    async startRhythm(pattern = 'kick ~ hihat ~') {
        this.strudel.init(pattern);
        await this.strudel.playPattern(4);
    }

    // Stop rhythm
    stopRhythm() {
        this.strudel.stop();
    }
}

// Demo/Test
async function demo() {
    console.log('=== Strudel Voice Mode Bridge Demo ===\n');
    
    const integration = new VoiceModeHookIntegration();
    
    // Simulate tool triggers
    const tools = ['bash', 'grep', 'read', 'write', 'edit'];
    
    console.log('Simulating tool triggers...\n');
    
    for (const tool of tools) {
        await integration.onToolTrigger(tool);
        await new Promise(resolve => setTimeout(resolve, 500));
    }
    
    console.log('\nStarting background rhythm...\n');
    await integration.startRhythm();
    
    console.log('\nDemo complete!');
}

// Export for use in voice mode
export { VoiceModeStrudel, VoiceModeHookIntegration };

// Run demo if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
    demo().catch(console.error);
}