from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
import re
import time
from datetime import datetime
from pathlib import Path

from backend.core.llm import ollama_client
from backend.config import settings

CHUNK_BUFFER_SIZE = 10
CHUNK_FLUSH_INTERVAL = 0.05

SENTENCE_END_PATTERN = re.compile(r"(?<=[.!?])\s+")

voice_enabled = False
speak_func = None
speak_sentence_func = None
voice_service = None
reset_stop_func = None
strip_emojis_func = None

try:
    from backend.core.voice import voice_service as _voice_service
    from backend.core.voice import conversational_service as _conversational_service
    from backend.core.tts import (
        speak as _speak,
        speak_sentence as _speak_sentence,
        reset_stop_flag as _reset_stop,
        strip_emojis as _strip_emojis,
        presynthesize as _presynthesize,
        play_presynthesized as _play_presynthesized,
    )

    voice_service = _voice_service
    conversational_service = _conversational_service
    speak_func = _speak
    speak_sentence_func = _speak_sentence
    reset_stop_func = _reset_stop
    strip_emojis_func = _strip_emojis
    presynthesize_func = _presynthesize
    play_presynthesized_func = _play_presynthesized
    voice_enabled = True
except ImportError as e:
    print(f"Voice modules not available: {e}")
    presynthesize_func = None
    play_presynthesized_func = None
    conversational_service = None


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.conversation_history: dict[str, list[dict]] = {}
        self.stop_flags: dict[str, bool] = {}
        self.muted: dict[str, bool] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        if client_id not in self.conversation_history:
            self.conversation_history[client_id] = []
        self.stop_flags[client_id] = False
        self.muted[client_id] = True

    def disconnect(self, websocket: WebSocket, client_id: str):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    def get_history(self, client_id: str) -> list[dict]:
        return self.conversation_history.get(client_id, [])

    def add_message(self, client_id: str, role: str, content: str):
        if client_id not in self.conversation_history:
            self.conversation_history[client_id] = []
        self.conversation_history[client_id].append({"role": role, "content": content})
        if len(self.conversation_history[client_id]) > 40:
            self.conversation_history[client_id] = self.conversation_history[client_id][-40:]

        if len(self.conversation_history[client_id]) % 10 == 0:
            save_conversation_to_file(client_id, self.conversation_history[client_id])

    def clear_history(self, client_id: str):
        if client_id in self.conversation_history and self.conversation_history[client_id]:
            save_conversation_to_file(client_id, self.conversation_history[client_id])
        self.conversation_history[client_id] = []

    def request_stop(self, client_id: str):
        self.stop_flags[client_id] = True

    def should_stop(self, client_id: str) -> bool:
        return self.stop_flags.get(client_id, False)

    def reset_stop(self, client_id: str):
        self.stop_flags[client_id] = False

    def set_muted(self, client_id: str, muted: bool):
        self.muted[client_id] = muted

    def is_muted(self, client_id: str) -> bool:
        return self.muted.get(client_id, True)


manager = ConnectionManager()


def save_conversation_to_file(client_id: str, messages: list[dict]):
    if not messages:
        return
    try:
        conv_dir = settings.conversations_dir
        conv_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = conv_dir / f"conversation_{client_id}_{timestamp}.json"
        data = {
            "client_id": client_id,
            "saved_at": datetime.now().isoformat(),
            "message_count": len(messages),
            "messages": messages,
        }
        filename.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"[CONV] Saved conversation to {filename.name}")
    except Exception as e:
        print(f"[CONV] Failed to save conversation: {e}")


def extract_complete_sentences(text: str) -> tuple[list[str], str]:
    sentences = []
    current = ""

    for char in text:
        current += char
        if char in ".!?" and len(current.strip()) > 5:
            sentences.append(current.strip())
            current = ""

    return sentences, current


async def websocket_endpoint(websocket: WebSocket, client_id: str = "default"):
    await manager.connect(websocket, client_id)

    async def send_message(msg_type: str, **data):
        await websocket.send_text(json.dumps({"type": msg_type, **data}))

    async def handle_generation(user_content: str):
        manager.add_message(client_id, "user", user_content)
        manager.reset_stop(client_id)

        if reset_stop_func:
            reset_stop_func()

        await send_message("start", role="assistant")
        print(f"[WS] Starting generation for: {user_content[:50]}...")

        history = manager.get_history(client_id)
        full_response = ""
        chunk_buffer = ""
        last_flush_time = asyncio.get_event_loop().time()
        was_stopped = False

        should_speak = voice_enabled and speak_sentence_func and not manager.is_muted(client_id)
        print(
            f"[DEBUG] should_speak={should_speak}, voice_enabled={voice_enabled}, muted={manager.is_muted(client_id)}"
        )
        speech_buffer = ""
        sentences_to_speak: asyncio.Queue = asyncio.Queue()
        synth_results: asyncio.Queue = asyncio.Queue()
        speech_task = None
        synth_task = None

        llm_start = time.perf_counter()
        first_token_time = None
        token_count = 0

        async def synthesis_worker():
            while True:
                try:
                    item = await asyncio.wait_for(sentences_to_speak.get(), timeout=0.1)
                    if item is None:
                        await synth_results.put(None)
                        break
                    if manager.should_stop(client_id):
                        await synth_results.put(None)
                        break

                    sentence, lang = item
                    synth_start = time.perf_counter()
                    wav_path = (
                        await presynthesize_func(sentence, lang) if presynthesize_func else None
                    )
                    synth_time = time.perf_counter() - synth_start
                    print(f"[TIMING] TTS synth: {synth_time:.2f}s for {len(sentence)} chars")
                    await synth_results.put(wav_path)
                    sentences_to_speak.task_done()
                except asyncio.TimeoutError:
                    if manager.should_stop(client_id):
                        await synth_results.put(None)
                        break
                    continue
                except Exception as e:
                    print(f"Synthesis worker error: {e}")
                    await synth_results.put(None)
                    break

        async def playback_worker():
            speaking_started = False
            while True:
                try:
                    wav_path = await asyncio.wait_for(synth_results.get(), timeout=0.1)
                    if wav_path is None:
                        break
                    if manager.should_stop(client_id):
                        if wav_path and hasattr(wav_path, "unlink"):
                            wav_path.unlink(missing_ok=True)
                        break

                    if not speaking_started:
                        speaking_started = True
                        await send_message("voice_state", state="speaking")

                    if play_presynthesized_func and wav_path:
                        await play_presynthesized_func(wav_path)
                    synth_results.task_done()
                except asyncio.TimeoutError:
                    if manager.should_stop(client_id):
                        break
                    continue
                except Exception as e:
                    print(f"Playback worker error: {e}")
                    break

            if speaking_started:
                await send_message("voice_state", state="idle")

        if should_speak and presynthesize_func and play_presynthesized_func:
            print("[DEBUG] Starting TTS workers for voice output")
            synth_task = asyncio.create_task(synthesis_worker())
            speech_task = asyncio.create_task(playback_worker())
        else:
            print(
                f"[DEBUG] TTS workers NOT started: presynth={presynthesize_func is not None}, play={play_presynthesized_func is not None}"
            )

        try:
            async for chunk in ollama_client.generate_stream(history):
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                    ttft = first_token_time - llm_start
                    print(f"[TIMING] Time to first token: {ttft:.2f}s")

                token_count += 1

                if manager.should_stop(client_id):
                    was_stopped = True
                    break

                full_response += chunk
                chunk_buffer += chunk

                if should_speak:
                    speech_buffer += chunk
                    complete_sentences, speech_buffer = extract_complete_sentences(speech_buffer)
                    for sentence in complete_sentences:
                        cleaned = strip_emojis_func(sentence) if strip_emojis_func else sentence
                        if cleaned.strip():
                            await sentences_to_speak.put((cleaned.strip(), None))

                current_time = asyncio.get_event_loop().time()
                should_flush = (
                    len(chunk_buffer) >= CHUNK_BUFFER_SIZE
                    or (current_time - last_flush_time) >= CHUNK_FLUSH_INTERVAL
                    or chunk.endswith(("\n", ".", "!", "?", ":", ";"))
                )

                if should_flush and chunk_buffer:
                    await send_message("chunk", content=chunk_buffer)
                    chunk_buffer = ""
                    last_flush_time = current_time

            if chunk_buffer:
                await send_message("chunk", content=chunk_buffer)

            if should_speak and speech_buffer.strip() and not was_stopped:
                cleaned = strip_emojis_func(speech_buffer) if strip_emojis_func else speech_buffer
                if cleaned.strip():
                    await sentences_to_speak.put((cleaned.strip(), None))

            if should_speak:
                await sentences_to_speak.put(None)
                if synth_task:
                    await synth_task
                if speech_task:
                    await speech_task

            if full_response:
                manager.add_message(client_id, "assistant", full_response)
                # Learn from conversation
                try:
                    from backend.memory.profile import user_profile
                    from backend.memory.brain import extract_and_learn, brain

                    user_profile.reload()
                    user_profile.update_from_chat(user_content, full_response)

                    history = manager.get_history(client_id)
                    if len(history) >= 2:
                        print(f"[WS] Starting brain extraction for history length: {len(history)}")

                        async def handle_memory_result():
                            try:
                                result = await extract_and_learn(history[-4:])
                                if result and isinstance(result, dict) and result.get("success"):
                                    msg = result.get("message", "")
                                    if msg:
                                        await send_message("chunk", content=f"\n\n{msg}")
                                        await send_message("memory_update", message=msg)
                                        print(f"[WS] Memory response sent: {msg}")
                            except Exception as e:
                                print(f"[WS] Memory result handling error: {e}")

                        asyncio.create_task(handle_memory_result())
                    else:
                        print(
                            f"[WS] Not enough history for brain extraction: {len(history) if history else 0} messages"
                        )

                    if len(history) >= 6 and len(history) % 6 == 0:
                        summary_text = f"User asked about: {user_content[:100]}"
                        user_profile.add_chat_summary(summary_text)
                        print(f"[WS] Added chat summary")

                    print(f"[WS] Brain data after learning: {brain.data}")
                except Exception as e:
                    print(f"[WS] Memory learning error: {e}")
                    import traceback

                    traceback.print_exc()

            llm_total = time.perf_counter() - llm_start
            if token_count > 0:
                tokens_per_sec = token_count / llm_total
                print(
                    f"[TIMING] LLM total: {llm_total:.2f}s, {token_count} tokens, {tokens_per_sec:.1f} tok/s"
                )

            await send_message("end", stopped=was_stopped)

        except Exception as e:
            print(f"Generation error: {e}")
            import traceback

            traceback.print_exc()
            await send_message("chunk", content=f"Error: {str(e)}")
            await send_message("end", stopped=True)
        except asyncio.CancelledError:
            if full_response:
                manager.add_message(client_id, "assistant", full_response)
                try:
                    from backend.memory.profile import user_profile

                    user_profile.update_from_chat(user_content, full_response)
                except Exception:
                    pass
            await send_message("end", stopped=True)
        finally:
            if should_speak:
                await sentences_to_speak.put(None)
                if synth_task and not synth_task.done():
                    synth_task.cancel()
                    try:
                        await synth_task
                    except asyncio.CancelledError:
                        pass
                if speech_task and not speech_task.done():
                    await synth_results.put(None)
                    speech_task.cancel()
                    try:
                        await speech_task
                    except asyncio.CancelledError:
                        pass

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            print(f"[WS] Received: {msg_type} from {client_id}")

            if msg_type == "stop":
                manager.request_stop(client_id)
                if voice_enabled and voice_service:
                    voice_service.stop_speaking()
                    voice_service.cancel_listening()
                continue

            if msg_type == "clear":
                manager.request_stop(client_id)
                manager.clear_history(client_id)
                await send_message("system", content="Conversation cleared.")
                continue

            if msg_type == "chat":
                user_content = message.get("content", "")
                print(f"[WS] Chat message: {user_content[:50]}...")
                if user_content.strip():
                    asyncio.create_task(handle_generation(user_content))
                continue

            if msg_type == "mute":
                muted = message.get("muted", True)
                manager.set_muted(client_id, muted)
                if voice_enabled and voice_service:
                    voice_service.set_muted(muted)
                    if muted:
                        voice_service.stop_speaking()
                        voice_service.cancel_listening()
                await send_message("voice_state", state="muted" if muted else "idle")
                continue

            if msg_type == "voice_start":
                print(f"[WS] Voice start requested, muted={manager.is_muted(client_id)}")
                if manager.is_muted(client_id):
                    await send_message("voice_state", state="muted")
                    continue
                if voice_enabled and voice_service:
                    try:
                        await voice_service.start_listening()
                        await send_message("voice_state", state="listening")
                        print("[WS] Voice listening started")
                    except Exception as e:
                        print(f"[WS] Voice start error: {e}")
                        await send_message("voice_state", state="idle")
                continue

            if msg_type == "voice_stop":
                print("[WS] Voice stop requested")
                if voice_enabled and voice_service:
                    try:
                        await send_message("voice_state", state="processing")
                        stt_start = time.perf_counter()
                        text = await voice_service.stop_listening()
                        stt_time = time.perf_counter() - stt_start
                        print(f"[TIMING] STT took {stt_time:.2f}s")
                        print(f"[WS] Transcription result: {text}")
                        if text:
                            await send_message("transcription", content=text)
                            asyncio.create_task(handle_generation(text))
                        else:
                            await send_message("voice_state", state="idle")
                    except Exception as e:
                        print(f"[WS] Voice stop error: {e}")
                        await send_message("voice_state", state="idle")
                continue

            if msg_type == "voice_cancel":
                if voice_enabled and voice_service:
                    voice_service.cancel_listening()
                    voice_service.stop_speaking()
                await send_message("voice_state", state="idle")
                continue

            if msg_type == "conv_start":
                print(f"[WS] Conversational mode start requested")
                if voice_enabled and conversational_service:
                    manager.set_muted(client_id, False)

                    def on_conv_state_change(state):
                        asyncio.create_task(send_message("voice_state", state=state.value))

                    async def on_conv_transcription(text: str):
                        print(f"[WS] Conv transcription: {text}")
                        await send_message("transcription", content=text)
                        await handle_generation(text)

                    conversational_service.on_state_change = on_conv_state_change
                    conversational_service.on_transcription = on_conv_transcription

                    try:
                        await conversational_service.start()
                        await send_message("voice_state", state="listening")
                        print("[WS] Conversational mode started")
                    except Exception as e:
                        print(f"[WS] Conv start error: {e}")
                        import traceback

                        traceback.print_exc()
                        await send_message("voice_state", state="idle")
                continue

            if msg_type == "conv_stop":
                print("[WS] Conversational mode stop requested")
                if voice_enabled and conversational_service:
                    try:
                        await conversational_service.stop()
                        await send_message("voice_state", state="idle")
                        print("[WS] Conversational mode stopped")
                    except Exception as e:
                        print(f"[WS] Conv stop error: {e}")
                continue

            if msg_type == "memory_search":
                try:
                    from backend.memory.vector import memory_store

                    query = message.get("query", "")
                    top_k = message.get("top_k", 5)
                    results = memory_store.search_knowledge(query, top_k)
                    await send_message("memory_search", results=results)
                except ImportError:
                    await send_message("error", content="Memory module not available")
                continue

            if msg_type == "memory_add":
                try:
                    from backend.memory.vector import memory_store

                    key = message.get("key", "")
                    value = message.get("value", "")
                    if key and value:
                        note = memory_store.add_note(key, value)
                        await send_message("memory_add", note=note)
                    else:
                        await send_message("error", content="key and value required")
                except ImportError:
                    await send_message("error", content="Memory module not available")
                continue

            if msg_type == "memory_get":
                try:
                    from backend.memory.vector import memory_store

                    note_id = message.get("id", "")
                    note = memory_store.get_note(note_id)
                    if note:
                        await send_message("memory_get", note=note)
                    else:
                        await send_message("error", content="Note not found")
                except ImportError:
                    await send_message("error", content="Memory module not available")
                continue

            if msg_type == "memory_update":
                try:
                    from backend.memory.vector import memory_store

                    note_id = message.get("id", "")
                    key = message.get("key")
                    value = message.get("value")
                    note = memory_store.update_note(note_id, key, value)
                    if note:
                        await send_message("memory_update", note=note)
                    else:
                        await send_message("error", content="Note not found")
                except ImportError:
                    await send_message("error", content="Memory module not available")
                continue

            if msg_type == "memory_delete":
                try:
                    from backend.memory.vector import memory_store

                    note_id = message.get("id", "")
                    if memory_store.delete_note(note_id):
                        await send_message("memory_delete", id=note_id)
                    else:
                        await send_message("error", content="Note not found")
                except ImportError:
                    await send_message("error", content="Memory module not available")
                continue

            if msg_type == "memory_list":
                try:
                    from backend.memory.vector import memory_store

                    notes = memory_store.list_notes()
                    await send_message("memory_list", notes=notes)
                except ImportError:
                    await send_message("error", content="Memory module not available")
                continue

    except WebSocketDisconnect:
        if conversational_service and conversational_service.is_running:
            await conversational_service.stop()
        if manager.conversation_history.get(client_id):
            save_conversation_to_file(client_id, manager.conversation_history[client_id])
        manager.disconnect(websocket, client_id)
    except Exception as e:
        try:
            await send_message("error", content=str(e))
        except Exception:
            pass
        manager.disconnect(websocket, client_id)
