# measure_blocks Skill Baseline — RED Phase

Date: 2026-07-04
Branch: feat/explicit-turn-handoff

## Purpose

Document verbatim baseline behavior BEFORE measure_blocks skill guidance is added.
Used for the RED-GREEN-REFACTOR skill writing cycle.

---

## Scenario 1: measure_blocks Trigger

**Setup:** Agent given voicemode SKILL (current version, no measure_blocks guidance).
User asks for per-block timing analysis of their speech patterns.

**Baseline behavior:**
- Agent did NOT set `measure_blocks=True`
- Rationalization: "존재하지 않거나 문서화되지 않은 파라미터를 추측으로 설정하면 오류가 발생하거나 의도치 않은 동작이 생길 수 있습니다"
- Agent instead used `⟨pause⟩` / `⟨pre-speech⟩` markers as a substitute
- Agent acknowledged: "제공된 SKILL 문서에 명시적으로 'measure_blocks 관련 가이드 없음'이라고 적혀 있고"

**Failure type:** Parameter unknown — agent cannot trigger what it doesn't know exists.
**Correct behavior:** When user wants per-block timing (how long each segment of speech
lasted, with gap durations), set `measure_blocks=True` on the next converse call.

---

## Scenario 2: Block Timeline Reading

**Setup:** Agent given voicemode SKILL. Presented with converse result:
```
Voice response: (gap 0.7s) 모델은 (5.3s) (gap 5.3s) 음 잘모르겠어요. 그... (6.3s) | Timing: 3.2s
```

**Baseline behavior:**
- Agent correctly identified `(gap 0.7s)` as pre-speech silence
- Agent MISREAD `(5.3s)` + `(gap 5.3s)` as "동일한 침묵을 다른 레이어로 중복 표현" (duplicate)
- Agent marked this as "포맷 버그일 수도" (possible format bug)
- Agent was uncertain: "확실하지 않습니다"

**Actual meaning (what agent should have said):**
- `(gap 0.7s)`: pre-speech gap — 0.7s before first word
- `모델은 (5.3s)`: speech block — the word "모델은" spoken, block duration 5.3s
- `(gap 5.3s)`: silence gap — 5.3s of silence between speech blocks
- `음 잘모르겠어요. 그... (6.3s)`: speech block — text + block duration 6.3s

**Key misunderstanding:** Agent confused "speech block duration" with "gap duration".
In `text (Ns)`, the `(Ns)` is the DURATION OF THAT SPEECH BLOCK, not a pause.
In `(gap Ns)`, the `(Ns)` is the duration of SILENCE between blocks.

**Failure type:** Format confusion — agent misreads `text (Ns)` as silence rather
than as "this speech segment lasted Ns seconds."

---

## Summary of Failures

| Scenario | Failure | Root Cause |
|----------|---------|------------|
| 1 | measure_blocks not set | Parameter unknown, no guidance on trigger condition |
| 2 | Misread `text (Ns)` as duplicate silence | No explanation of block timeline format |

## Required SKILL Additions

1. **Trigger condition** for `measure_blocks=True`:
   - When user wants per-block timing of how they speak
   - When user asks about speech patterns, hesitation, thinking gaps

2. **Reading the block timeline**:
   - `text (Ns)` = speech block: these words were spoken, block lasted Ns
   - `(gap Ns)` = silence between speech blocks, lasted Ns
   - Long block + few words = slow/stumbling speech
   - Long gap = thinking/hesitation between thoughts
   - Durations are seconds — agent judges patterns from them
