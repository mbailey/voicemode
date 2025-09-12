#!/usr/bin/env node

// Test if we can use Strudel patterns in Node.js without browser APIs

import { sequence, stack, note, s, Pattern } from '@strudel/core';

console.log('Testing Strudel Core in Node.js...\n');

// Test 1: Create a simple sequence pattern
const simplePattern = sequence('c3', 'd3', 'e3', 'f3');
console.log('Simple sequence pattern created');

// Test 2: Query events from the pattern
const events = simplePattern.queryArc(0, 1);
console.log(`Found ${events.length} events in first cycle:`);
events.forEach(event => {
    console.log(`  - Value: ${event.value}, Time: ${event.whole?.begin}-${event.whole?.end}`);
});

// Test 3: Create a more complex pattern with stacking
const drumPattern = stack(
    s('kick'),
    s('hihat').fast(2),
    s('snare').slow(2)
);
console.log('\nDrum pattern created');

// Test 4: Create a melodic pattern with notes
const melody = note('c3 e3 g3 [c4 b3]').slow(2);
console.log('Melodic pattern created');

// Test 5: Test pattern transformations
const transformed = simplePattern
    .fast(2)  // Play twice as fast
    .rev();   // Reverse the pattern

console.log('Pattern transformations applied');

// Test 6: Check if we can generate event data for voice mode hooks
console.log('\n=== Voice Mode Hook Integration Test ===');

// Simulate tool events that could trigger musical events
const toolEvents = ['bash', 'grep', 'read', 'write', 'edit'];
const toolSounds = {
    'bash': 'kick',
    'grep': 'hihat', 
    'read': 'snare',
    'write': 'clap',
    'edit': 'cowbell'
};

// Create a pattern that could respond to tool events
const toolPattern = s(toolEvents.map(t => toolSounds[t]).join(' '));
const toolEventsData = toolPattern.queryArc(0, 1);

console.log('Tool-triggered sound pattern:');
toolEventsData.forEach(event => {
    console.log(`  Tool sound: ${event.value}`);
});

console.log('\n✅ Strudel Core works in Node.js!');
console.log('Note: Audio playback requires Web Audio API or external audio engine');
console.log('Pattern generation and manipulation work without browser dependencies');