"""Audio device management tools."""

import logging
from typing import Optional
import sounddevice as sd

from voice_mode.server import mcp
from voice_mode.shared import startup_initialization

logger = logging.getLogger("voicemode")


@mcp.tool()
async def check_audio_devices() -> str:
    """List available audio input and output devices"""
    try:
        devices = sd.query_devices()
        input_devices = []
        output_devices = []
        
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                input_devices.append(f"  [{i}] {device['name']} ({device['max_input_channels']} channels)")
            if device['max_output_channels'] > 0:
                output_devices.append(f"  [{i}] {device['name']} ({device['max_output_channels']} channels)")
        
        default_input = sd.query_devices(kind='input')
        default_output = sd.query_devices(kind='output')
        
        result = []
        result.append("Audio Devices:")
        result.append(f"\nDefault Input: [{default_input['index']}] {default_input['name']}")
        result.append(f"Default Output: [{default_output['index']}] {default_output['name']}")
        
        result.append("\n\nInput Devices:")
        result.extend(input_devices)
        
        result.append("\n\nOutput Devices:")
        result.extend(output_devices)
        
        return "\n".join(result)
        
    except Exception as e:
        logger.error(f"Error listing audio devices: {e}")
        return f"Error listing audio devices: {str(e)}"


@mcp.tool()
async def voice_status() -> str:
    """Check the status of all voice services including TTS, STT, LiveKit, and audio devices.
    
    IMPORTANT: Only use this tool for debugging when voice services fail. The system has automatic 
    failover, so try using services directly first. This tool is for troubleshooting only.
    
    Provides a unified view of the voice infrastructure configuration and health.
    """
    from voice_mode.provider_discovery import provider_registry
    from voice_mode.config import TTS_BASE_URLS, STT_BASE_URLS
    
    try:
        # Ensure registry is initialized
        await provider_registry.initialize()
        
        status_lines = ["Voice Service Status:"]
        status_lines.append("=" * 50)
        
        # TTS Endpoints
        status_lines.append("\nTTS Endpoints:")
        for url in TTS_BASE_URLS:
            endpoint_info = provider_registry.registry["tts"].get(url)
            if endpoint_info:
                # Check if there's an error
                if endpoint_info.last_error:
                    status_lines.append(f"  ❌ {url}")
                    status_lines.append(f"     Error: {endpoint_info.last_error}")
                else:
                    status_lines.append(f"  ✅ {url}")
                    status_lines.append(f"     Models: {', '.join(endpoint_info.models[:3]) if endpoint_info.models else 'none'}")
                    status_lines.append(f"     Voices: {len(endpoint_info.voices)} available")
            else:
                status_lines.append(f"  ⚪ {url} (not discovered)")

        # STT Endpoints
        status_lines.append("\nSTT Endpoints:")
        for url in STT_BASE_URLS:
            endpoint_info = provider_registry.registry["stt"].get(url)
            if endpoint_info:
                # Check if there's an error
                if endpoint_info.last_error:
                    status_lines.append(f"  ❌ {url}")
                    status_lines.append(f"     Error: {endpoint_info.last_error}")
                else:
                    status_lines.append(f"  ✅ {url}")
                    status_lines.append(f"     Models: {', '.join(endpoint_info.models) if endpoint_info.models else 'none'}")
            else:
                status_lines.append(f"  ⚪ {url} (not discovered)")
        
        # Configuration
        from voice_mode.config import (
            TTS_VOICES, TTS_MODELS, 
            PREFER_LOCAL, AUTO_START_KOKORO,
            AUDIO_FEEDBACK_ENABLED, LIVEKIT_URL
        )
        
        status_lines.append("\nConfiguration:")
        status_lines.append(f"  Preferred Voices: {', '.join(TTS_VOICES[:3])}{'...' if len(TTS_VOICES) > 3 else ''}")
        status_lines.append(f"  Preferred Models: {', '.join(TTS_MODELS)}")
        status_lines.append(f"  Prefer Local: {PREFER_LOCAL}")
        status_lines.append(f"  Auto-start Kokoro: {AUTO_START_KOKORO}")
        status_lines.append(f"  Audio Feedback: {'Enabled' if AUDIO_FEEDBACK_ENABLED else 'Disabled'}")
        status_lines.append(f"  LiveKit URL: {LIVEKIT_URL}")
        
        # Audio devices
        try:
            default_input = sd.query_devices(kind='input')
            default_output = sd.query_devices(kind='output')
            status_lines.append("\nAudio Devices:")
            status_lines.append(f"  Input: {default_input['name']}")
            status_lines.append(f"  Output: {default_output['name']}")
        except:
            status_lines.append("\nAudio Devices: Unable to query")
        
        return "\n".join(status_lines)
        
    except Exception as e:
        logger.error(f"Error getting voice status: {e}")
        return f"Error getting voice status: {str(e)}"


@mcp.tool()
async def list_tts_voices(provider: Optional[str] = None) -> str:
    """List available TTS voices for different providers.
    
    Args:
        provider: Optional provider name ('openai' or 'kokoro'). If not specified, lists all available voices.
    
    Returns:
        A formatted list of available voices by provider.
    """
    await startup_initialization()
    
    results = []
    results.append("🔊 AVAILABLE TTS VOICES")
    results.append("=" * 40)
    
    # Determine which providers to check
    providers_to_check = []
    if provider:
        if provider.lower() not in ['openai', 'kokoro']:
            return f"Error: Unknown provider '{provider}'. Valid options: 'openai', 'kokoro'"
        providers_to_check = [provider.lower()]
    else:
        providers_to_check = ['openai', 'kokoro']
    
    # OpenAI voices
    if 'openai' in providers_to_check:
        results.append("\n📢 OpenAI Voices")
        results.append("-" * 40)
        
        # Standard voices (work with all models)
        results.append("\n**Standard Voices** (tts-1, tts-1-hd):")
        standard_voices = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
        for voice in standard_voices:
            results.append(f"  • {voice}")
        
        # Enhanced voices for gpt-4o-mini-tts
        results.append("\n**Enhanced Voices** (gpt-4o-mini-tts):")
        enhanced_voices = ['alloy', 'echo', 'shimmer']
        for voice in enhanced_voices:
            results.append(f"  • {voice} - supports emotional expression")
        
        results.append("\n**Voice Characteristics**:")
        voice_descriptions = {
            'alloy': 'Natural and conversational (default)',
            'echo': 'Smooth and conversational', 
            'fable': 'British accent, authoritative',
            'onyx': 'Deep and authoritative',
            'nova': 'Warm and friendly',
            'shimmer': 'Expressive and engaging'
        }
        for voice, desc in voice_descriptions.items():
            results.append(f"  • {voice}: {desc}")
    
    # Kokoro voices
    if 'kokoro' in providers_to_check:
        results.append("\n\n🎭 Kokoro Voices (67 voices available)")
        results.append("-" * 40)
        
        results.append("\n**Voice Naming Convention**:")
        results.append("  • af_ = American Female")
        results.append("  • am_ = American Male")
        results.append("  • bf_ = British Female")
        results.append("  • bm_ = British Male")
        results.append("  • ef_ = Spanish Female")
        results.append("  • em_ = Spanish Male")
        results.append("  • ff_ = French Female")
        results.append("  • hf_ = Hindi Female")
        results.append("  • hm_ = Hindi Male")
        results.append("  • if_ = Italian Female")
        results.append("  • im_ = Italian Male")
        results.append("  • jf_ = Japanese Female")
        results.append("  • jm_ = Japanese Male")
        results.append("  • pf_ = Portuguese Female")
        results.append("  • pm_ = Portuguese Male")
        results.append("  • zf_ = Chinese Female")
        results.append("  • zm_ = Chinese Male")
        
        results.append("\n**Recommended Voices**:")
        kokoro_recommended = {
            'af_sky': 'American Female - Natural and expressive (default)',
            'af_sarah': 'American Female - Warm and friendly',
            'am_adam': 'American Male - Clear and professional',
            'bf_emma': 'British Female - Sophisticated accent',
            'bm_george': 'British Male - Distinguished accent',
            'ef_dora': 'Spanish Female - Clear and expressive',
            'em_alex': 'Spanish Male - Natural voice'
        }
        for voice, desc in kokoro_recommended.items():
            results.append(f"  • {voice}: {desc}")
        
        results.append("\n**All Available Voices by Language**:")
        
        # American voices
        results.append("\n  American Female (18 voices):")
        results.append("    af_alloy, af_aoede, af_bella, af_heart, af_jadzia, af_jessica,")
        results.append("    af_kore, af_nicole, af_nova, af_river, af_sarah, af_sky,")
        results.append("    af_v0, af_v0bella, af_v0irulan, af_v0nicole, af_v0sarah, af_v0sky")
        
        results.append("\n  American Male (12 voices):")
        results.append("    am_adam, am_echo, am_eric, am_fenrir, am_liam, am_michael,")
        results.append("    am_onyx, am_puck, am_santa, am_v0adam, am_v0gurney, am_v0michael")
        
        # British voices
        results.append("\n  British Female (5 voices):")
        results.append("    bf_alice, bf_emma, bf_lily, bf_v0emma, bf_v0isabella")
        
        results.append("\n  British Male (6 voices):")
        results.append("    bm_daniel, bm_fable, bm_george, bm_lewis, bm_v0george, bm_v0lewis")
        
        # Other languages
        results.append("\n  Spanish (3 voices): ef_dora, em_alex, em_santa")
        results.append("  French (1 voice): ff_siwis")
        results.append("  Hindi (4 voices): hf_alpha, hf_beta, hm_omega, hm_psi")
        results.append("  Italian (2 voices): if_sara, im_nicola")
        results.append("  Japanese (5 voices): jf_alpha, jf_gongitsune, jf_nezumi, jf_tebukuro, jm_kumo")
        results.append("  Portuguese (3 voices): pf_dora, pm_alex, pm_santa")
        results.append("  Chinese (8 voices): zf_xiaobei, zf_xiaoni, zf_xiaoxiao, zf_xiaoyi,")
        results.append("                      zm_yunjian, zm_yunxi, zm_yunxia, zm_yunyang")
    
    return "\n".join(results)