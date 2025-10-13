# Non-English Language Support

## Overview

When speaking non-English languages, you **must** specify both `voice` and `tts_provider` for proper pronunciation. Default OpenAI voices speak non-English with an American accent.

## Recommended Kokoro Voices

### Spanish
```python
converse("¿Cómo estás?", voice="ef_dora", tts_provider="kokoro")
```

### French
```python
converse("Bonjour!", voice="ff_siwis", tts_provider="kokoro")
```

### Italian
```python
converse("Ciao!", voice="if_sara", tts_provider="kokoro")
```

### Chinese
```python
converse("你好", voice="zf_xiaobei", tts_provider="kokoro")
```

### Japanese
```python
converse("こんにちは", voice="jf_alpha", tts_provider="kokoro")
```

## Available Kokoro Voices by Language

### English
- `af_sky` - Female
- `af_sarah` - Female
- `am_adam` - Male
- `am_michael` - Male

### Spanish
- `ef_dora` - Female
- `em_marco` - Male

### French
- `ff_siwis` - Female
- `fm_jean` - Male

### Italian
- `if_sara` - Female
- `im_marco` - Male

### Chinese (Mandarin)
- `zf_xiaobei` - Female
- `zm_xiaoming` - Male

### Japanese
- `jf_alpha` - Female
- `jm_beta` - Male

### German
- `gf_lisa` - Female
- `gm_hans` - Male

### Portuguese (Brazilian)
- `bf_maria` - Female
- `bm_joao` - Male

### Russian
- `rf_natasha` - Female
- `rm_dmitri` - Male

### Korean
- `kf_yuna` - Female
- `km_junho` - Male

### Hindi
- `hf_priya` - Female
- `hm_raj` - Male

### Arabic
- `af_layla` - Female
- `am_omar` - Male

### Turkish
- `tf_ayse` - Female
- `tm_mehmet` - Male

## Voice Naming Convention

Kokoro voices follow the pattern: `{language}{gender}_{name}`

- **Language code:** First letter(s) of language
  - `a` = English (American)
  - `e` = Spanish (Español)
  - `f` = French (Français)
  - `i` = Italian
  - `z` = Chinese (中文)
  - `j` = Japanese
  - `g` = German
  - `b` = Brazilian Portuguese
  - `r` = Russian
  - `k` = Korean
  - `h` = Hindi
  - `t` = Turkish

- **Gender:**
  - `f` = Female
  - `m` = Male

- **Name:** Given name in that language

## OpenAI Voices (English-centric)

OpenAI voices work for any language but maintain American English accent:
- `nova` - Female
- `shimmer` - Female
- `alloy` - Neutral
- `echo` - Male
- `fable` - Male
- `onyx` - Male

**Not recommended for non-English** - use Kokoro instead.

## Important Notes

1. **Always specify both `voice` and `tts_provider`** when using non-English
2. **Never use `coral` voice** - it's not supported
3. Kokoro provides native pronunciation for each language
4. STT (speech-to-text) automatically detects language

## See Also
- `voicemode-parameters` - Full parameter reference
- `voicemode-quickstart` - Basic usage examples
