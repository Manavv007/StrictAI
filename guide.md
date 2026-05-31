────────────────────────────

  1. Current state

  What you already have (good foundations):

  ┌───────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Layer         │ Today                                                                                              │
  ├───────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ System prompt │ Large INSTRUCTIONS block (~90 lines) — most interview rules live here only                         │
  │ Time          │ on_user_turn_completed injects [TIME_STATUS_ENFORCEMENT] and hard-stops on ending / auto_end       │
  │ enforcement   │                                                                                                    │
  │ Tool          │ select_next_objective, score_answer, timer-driven end_interview                                    │
  │ discipline    │                                                                                                    │
  │ Observability │ PostHog via                                                                                        │
  │               │ [posthog_tracker.py](livekit-interview-agent/livekit_interview_agent/posthog_tracker.py), latency  │
  │               │ tracker                                                                                            │
  └───────────────┴────────────────────────────────────────────────────────────────────────────────────────────────────┘

  What is missing:

  • No NeMo Guardrails
  • No output gate before TTS (LLM violations can be spoken)
  • No input jailbreak / PII handling on user speech
  • No structured violation logging

  Important: LiveKit Agents 1.3 does not ship a class named Observer. The equivalent is pipeline hooks + node overrides:
   on_user_turn_completed, llm_node, tts_node, transcription_node, and session.on("conversation_item_added", ...).

  ────────────────────────────────────────

  2. Target architecture (layered defense)

  mermaid flowchart

  flowchart TB
    subgraph input [User turn]
      STT[STT]
      FastIn[Fast input checks regex PII jailbreak]
      NeMoIn[NeMo input rails parallel]
      Hook[on_user_turn_completed time inject]
    end
    subgraph llm [Generation]
      Prompt[Trimmed system prompt]
      LLM[Groq / Gemini FallbackAdapter]
      Tools[select_next_objective score_answer]
    end
    subgraph output [Agent reply]
      FastOut[Fast output checks hints praise multi-Q]
      NeMoOut[NeMo output rails parallel streaming]
      TTSGate[tts_node gate safe text only]
      TTS[Deepgram TTS]
    end
    subgraph obs [Observability]
      Log[structured violation logs]
      PH[PostHog guardrail_violation]
    end
    STT --> FastIn --> NeMoIn --> Hook --> Prompt --> LLM --> Tools
    LLM --> FastOut --> NeMoOut --> TTSGate --> TTS
    FastIn --> Log
    NeMoIn --> Log
    FastOut --> Log
    NeMoOut --> Log
    Log --> PH

  Principle: Fast deterministic checks first (sub‑ms), NeMo check_async second (tens–hundreds of ms), prompt last
  (behavior, not safety).

  ────────────────────────────────────────

  3. What to move out of INSTRUCTIONS into guardrails

  Keep in prompt (behavior / flow): tone, bridges, objective selection strategy, wrap-up phrasing variety, resume
  grounding, tool call order.

  Move to guardrails (enforceable, testable):

  ┌───────────────────────────────────────────────────┬───────────────────────────────────────────┐
  │ Rule (from your prompt)                           │ Guardrail type                            │
  ├───────────────────────────────────────────────────┼───────────────────────────────────────────┤
  │ No hints, solutions, code, walkthroughs           │ Output rail + fast regex                  │
  │ No praise/judgment ("great", "correct", "wrong")  │ Output rail + word list                   │
  │ Exactly one ? per turn (except scripted opening)  │ Fast output check                         │
  │ Never reveal scores, objectives, evaluation       │ Output rail                               │
  │ No early interview end / no hire-reject authority │ Input rail (user jailbreak) + output rail │
  │ Redirect off-topic / adversarial / jailbreak      │ Input rail                                │
  │ PII handling (email, phone, SSN patterns)         │ Input mask rail + output block            │
  │ No teaching/explaining technical concepts         │ Output LLM self-check                     │
  │ ending / auto_end: no new questions               │ Keep in code (you already do this well)   │
  └───────────────────────────────────────────────────┴───────────────────────────────────────────┘

  Your timer hook is already stronger than Colang for time — do not duplicate ending logic in NeMo; pass phase in
  context only for output rails during wrap_up.

  ────────────────────────────────────────

  4. Proposed folder structure

  livekit-interview-agent/
  ├── guardrails_config/                    # NeMo RailsConfig root
  │   ├── config.yml
  │   ├── actions/
  │   │   └── interview_actions.py          # @action fast checks
  │   ├── rails/
  │   │   ├── input.co                      # jailbreak, off-topic, PII
  │   │   ├── output.co                     # hints, praise, multi-question, eval leak
  │   │   └── interview_redirect.co         # bot safe redirect lines
  │   └── prompts.yml                       # optional: rail-only LLM prompts
  ├── livekit_interview_agent/
  │   ├── guardrails/
  │   │   ├── __init__.py
  │   │   ├── client.py                     # LLMRails singleton, check_async wrappers
  │   │   ├── fast_checks.py                # regex/heuristics (no NeMo call)
  │   │   ├── violation_logger.py           # structured logs + PostHog
  │   │   └── output_gate.py                # tts_node wrapper / text buffer
  │   └── agent.py                          # wire hooks (minimal diff)
  └── tests/
      └── test_guardrails_fast_checks.py

  Dependency (add to pyproject.toml (livekit-interview-agent/pyproject.toml)):

  "nemoguardrails>=0.21.0"

  Optional dev group for Colang/NIM integration tests.

  ────────────────────────────────────────

  5. NeMo config.yml (sketch)

  Use a small, fast rail model separate from the interview LLM (Groq/Gemini). Do not run full generate() on every turn —
   use check_async() only.

  # guardrails_config/config.yml
  models:
    - type: main
      engine: openai          # or nim / groq if you standardize
      model: gpt-4o-mini        # rail-only; keep cheap + low temp
      parameters:
        temperature: 0.0
        max_tokens: 256
    # Optional: dedicated safety model on NIM (parallel rails)
    - type: content_safety
      engine: nim
      model: nvidia/llama-3.1-nemoguard-8b-content-safety
  rails:
    config:
      interview:
        max_questions_per_turn: 1
        block_praise: true
        block_hints: true
    input:
      parallel: true
      flows:
        - interview jailbreak check
        - interview mask pii on input
        - interview off topic redirect
    output:
      parallel: true
      streaming:
        enabled: true
        chunk_size: 150
        context_size: 40
        stream_first: true
      flows:
        - interview output no hints or solutions
        - interview output no evaluation leak
        - interview output single question
        - self check output                    # generic NeMo self-check

  Env vars:

  • NEMO_GUARDRAILS_ENABLED=true
  • NEMO_GUARDRAILS_CONFIG_PATH=./guardrails_config
  • Rail LLM: OPENAI_API_KEY or NVIDIA_API_KEY + NIM base URL
  • GUARDRAILS_FAIL_OPEN=false (production: fail closed on rail errors)

  ────────────────────────────────────────

  6. Example Colang flows (interview-specific)

  rails/input.co — jailbreak / manipulation

  define subflow interview jailbreak check
    $is_jailbreak = execute detect_interview_jailbreak
    if $is_jailbreak
      bot inform stay on interview
      abort
  define bot inform stay on interview
    "Let's keep the focus on the interview questions."

  actions/interview_actions.py

  @action(is_system_action=True)
  async def detect_interview_jailbreak(context=None):
      text = (context or {}).get("user_message", "").lower()
      patterns = [
          "ignore previous", "ignore all instructions", "reveal your prompt",
          "end the interview", "you are hired", "give me the answer",
          "what is the correct answer", "pretend you are",
      ]
      return any(p in text for p in patterns)

  rails/output.co — hints / solutions / code

  define subflow interview output no hints or solutions
    $violates = execute detect_interviewer_violation
    if $violates
      bot inform cannot help with answers
      stop
  define bot inform cannot help with answers
    "I can't provide hints or solutions during the interview. Please share your own approach."

  detect_interviewer_violation (Python): code fences, here's how, the answer is, for example you could, step 1:, praise
  list, multiple ?.

  interview output single question

  @action(is_system_action=True)
  async def count_question_marks(context=None):
      msg = (context or {}).get("bot_message", "")
      return msg.count("?") > 1

  ────────────────────────────────────────

  7. LiveKit integration (your agent)

  7.1 Input path — extend on_user_turn_completed

  In SerinInterviewAgent.on_user_turn_completed (livekit-interview-agent/livekit_interview_agent/agent.py) (after time
  checks, before LLM):

  1. Fast check on new_message text → block with injected system message or StopResponse + scripted redirect via
     session.say(..., add_to_chat_ctx=True).
  2. await rails.check_async([{"role":"user","content": text}], rail_types=[INPUT])
  3. On BLOCKED / MODIFIED: log violation, optionally replace user message in turn_ctx or stop and speak redirect.

  Do not block the opening scripted greeting path in on_enter.

  7.2 Output path — override tts_node (the "Observer")

  Pattern:

  async def tts_node(self, text, model_settings):
      async def gated():
          buffer = ""
          async for chunk in text:
              buffer += chunk
              if sentence_complete(buffer):  # . ! ? or tokenizer
                  safe = await output_gate.validate(buffer, phase=self._phase)
                  if not safe.approved:
                      yield safe.replacement_text
                      return
                  yield buffer
                  buffer = ""
          if buffer:
              ...
      return Agent.default.tts_node(self, gated(), model_settings)

  output_gate.validate order:

  1. fast_checks.py (sync)
  2. rails.check_async([user, assistant], rail_types=[OUTPUT]) only if fast check suspicious OR every Nth turn
     (configurable)
  3. On failure: fixed redirect string (no second LLM call in hot path)

  7.3 Optional: transcription_node

  Use for logging/transcript accuracy; primary enforcement stays on tts_node so bad text never reaches audio.

  7.4 conversation_item_added (audit only)

  Extend PostHog tracker or add listener:

  • On role=assistant, run fast checks post-hoc
  • Emit guardrail_violation even if gate caught it (dedupe by speech_id)

  7.5 What stays in code (do not move to NeMo)

  • _compute_interview_time_status + StopResponse on ending / auto_end
  • _execute_end_interview_flow
  • Opening question skip in score_answer
  • Tool-only end interview (disabled) — good

  ────────────────────────────────────────

  8. Low-latency strategy

  ┌──────────────────────────────────────────┬────────────────────────────────────────────────────────┐
  │ Technique                                │ Impact                                                 │
  ├──────────────────────────────────────────┼────────────────────────────────────────────────────────┤
  │ check_async not generate                 │ Avoid double full LLM interview turn                   │
  │ Dedicated small rail model               │ 200–400 ms vs multi-second main model                  │
  │ rails.input/output.parallel: true        │ Wall time = max(rail), not sum                         │
  │ Fast path skips NeMo when regex clean    │ ~0 ms for most turns                                   │
  │ Output streaming rails (chunk_size: 150) │ Catch violations before full reply is spoken           │
  │ Run input rails while LLM tools execute  │ Overlap select_next_objective + input check where safe │
  │ Warm LLMRails in prewarm()               │ Amortize config load per worker process                │
  │ Cache last input hash                    │ Skip repeat checks on duplicate STT glitches           │
  └──────────────────────────────────────────┴────────────────────────────────────────────────────────┘

  Avoid: Running NeMo on every TTS token; running same model as Groq 120B for rails.

  ────────────────────────────────────────

  9. Observability

  Structured log (every violation):

  {
    "event": "guardrail_violation",
    "session_id": "...",
    "rail_layer": "fast|nemo_input|nemo_output|code",
    "rail_name": "detect_interviewer_violation",
    "action": "block|replace|redirect",
    "phase": "normal|wrap_up",
    "user_text_hash": "sha256:...",
    "bot_text_preview": "first 120 chars"
  }

  PostHog: new event guardrail_violation with properties above (reuse PostHogTracker
  (livekit-interview-agent/livekit_interview_agent/posthog_tracker.py)).

  Metrics to dashboard:

  • Violations per session
  • Block rate by rail name
  • p95 check_async latency
  • False positive reports (manual tag)

  ────────────────────────────────────────

  10. Slimmed system prompt (after guardrails)

  Reduce INSTRUCTIONS (livekit-interview-agent/livekit_interview_agent/agent.py) by ~30–40%:

  • Remove repeated "no hints / no praise / one question" paragraphs (enforced by rails).
  • Keep conversation style, bridges, tool usage, resume/objective strategy, wrap-up variety examples.
  • Add one line: "Safety and interview boundaries are enforced by system policy; if redirected, comply briefly and
    continue."

  Scoring prompt in scoring.py (livekit-interview-agent/livekit_interview_agent/scoring.py) stays separate; optionally
  add output rail so scoring reasoning never leaks into spoken text (scoring is tool-internal only today — good).

  ────────────────────────────────────────

  11. Implementation phases

  ┌──────────────┬──────────────────────────────────────────────────────────────────────────┬──────────────────────────┐
  │ Phase        │ Deliverable                                                              │ Risk                     │
  ├──────────────┼──────────────────────────────────────────────────────────────────────────┼──────────────────────────┤
  │ P0           │ fast_checks.py + violation_logger.py + tts_node gate                     │ Low; immediate value     │
  │ P1           │ guardrails_config/ + client.py + input check_async in                    │ Medium; needs rail API   │
  │              │ on_user_turn_completed                                                   │ key                      │
  │ P2           │ Full Colang flows + parallel output streaming rails                      │ Medium                   │
  │ P3           │ Tests, PostHog dashboard, fail-open/closed flag, README                  │ Low                      │
  │ P4           │ NIM Nemoguard models for jailbreak/content                               │ Infra dependency         │
  │ (optional)   │                                                                          │                          │
  └──────────────┴──────────────────────────────────────────────────────────────────────────┴──────────────────────────┘

  ────────────────────────────────────────

  12. Decisions to confirm before coding

  1. Rail LLM provider: OpenAI mini, Groq small model, or NVIDIA NIM Nemoguard? (Affects config.yml and env vars.)
  2. Fail mode: On NeMo timeout/error, fail open (speak reply) vs fail closed (safe redirect)? Production interviews
     usually want fail closed for output, fail open only for input if latency critical.
  3. Scope of first PR: P0+P1 only (fast checks + input rails) vs full P0–P2?

  ────────────────────────────────────────

  13. What I would ask you next (when you want implementation)

  • Paste or confirm rail model choice (NIM vs Groq vs OpenAI).
  • Whether GKE deployment can add NVIDIA_API_KEY / rail model sidecar.
  • Any allowed exceptions (e.g. interviewer may clarify ambiguous question without it counting as a "hint").

  ────────────────────────────────────────

  Summary: Your agent already enforces time and tools in code. The biggest gap is spoken output leaving the LLM
  unchecked. Add NeMo as the main policy layer via check_async + Colang, fast regex as L1, and tts_node as the final
  gate — that is the production pattern for strict interview agents on LiveKit without adding hundreds of ms to every
  turn.