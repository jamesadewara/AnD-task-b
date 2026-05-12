import asyncio
import json
import re
import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from loguru import logger
from beanie import PydanticObjectId
from sse_starlette.sse import EventSourceResponse

from app.documents.chat import ChatSession, Message as ChatMessage, MessageFeedbackRequest
from app.core.security import get_user_id, get_user_id_from_anywhere
from app.schemas.chat import ChatUpdate, ChatResponse, ChatMessageRequest, ChatDetailsResponse
from app.managers.stream_manager import stream_manager

router = APIRouter()

@router.post("/{chat_id}/message/{message_id}/feedback", status_code=status.HTTP_200_OK)
async def submit_message_feedback(
    chat_id: str,
    message_id: str,
    payload: MessageFeedbackRequest,
    user_id: str = Depends(get_user_id),
):
    """
    Records a like/dislike on an AI message and updates the user's taste profile.
    Liked messages boost topic interests; disliked messages reduce them.
    """
    if not PydanticObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid Chat ID")

    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    from app.documents.user import UserDocument
    user = await UserDocument.find_by_id_or_uuid(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1. Store raw feedback signal
    user.message_feedback.append({
        "message_id": message_id,
        "chat_id": chat_id,
        "sentiment": payload.sentiment,
        "topics": payload.topics,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    })

    # 2. Update taste profile based on signal
    if payload.sentiment == "like" and payload.topics:
        current = set(user.taste_profile.interests)
        for t in payload.topics:
            current.add(t.lower())
        user.taste_profile.interests = list(current)[:50]  # cap at 50

    elif payload.sentiment == "dislike" and payload.topics:
        current = set(user.taste_profile.interests)
        for t in payload.topics:
            current.discard(t.lower())
        user.taste_profile.interests = list(current)

    await user.save()
    logger.info(f"Feedback '{payload.sentiment}' recorded for msg {message_id} by user {user_id}")
    return {"status": "ok", "sentiment": payload.sentiment}



@router.get("/", response_model=List[ChatResponse])
async def list_chats(user_id: str = Depends(get_user_id)):
    """Fetch all chat sessions for the current user."""
    chats = await ChatSession.find(ChatSession.user_id == user_id).to_list()
    return [ChatResponse.from_doc(c) for c in chats]

@router.post("/", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(user_id: str = Depends(get_user_id)):
    """Create a new chat session."""
    chat = ChatSession(user_id=user_id)
    await chat.insert()
    return ChatResponse.from_doc(chat)

@router.get("/{chat_id}", response_model=ChatDetailsResponse)
async def get_chat(chat_id: str, user_id: str = Depends(get_user_id)):
    """Fetch full details and message history for a specific chat."""
    if not PydanticObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid Chat ID format")
        
    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    return ChatDetailsResponse.from_doc(chat)

@router.patch("/{chat_id}", response_model=ChatResponse)
async def update_chat_name(
    chat_id: str, 
    payload: ChatUpdate, 
    user_id: str = Depends(get_user_id)
):
    """Update the name of a chat session."""
    if not PydanticObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid Chat ID format")
        
    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat.name = payload.name
    await chat.save()
    return ChatResponse.from_doc(chat)

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: str, user_id: str = Depends(get_user_id)):
    """Delete a chat session."""
    if not PydanticObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid Chat ID format")
        
    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    await chat.delete()
    return None

@router.post("/{chat_id}/message", status_code=status.HTTP_202_ACCEPTED)
async def send_message(
    chat_id: str, 
    payload: ChatMessageRequest, 
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id)
):
    """
    Accepts a message, saves it, and initializes a stream session.
    Returns 202 Accepted with a unique stream_id.
    The actual AI processing happens in a background task.
    """
    if not PydanticObjectId.is_valid(chat_id):
        raise HTTPException(status_code=400, detail="Invalid Chat ID format")
        
    chat = await ChatSession.get(chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Save User Message
    user_msg = ChatMessage(sender_id=user_id, content=payload.message or "[Guided Flow]")
    chat.messages.append(user_msg)
    await chat.save()

    # Create Stream Session
    session = await stream_manager.create_session(chat_id)
    
    # Trigger AI processing in background
    background_tasks.add_task(
        process_and_stream, 
        chat_id=chat_id, 
        user_id=user_id, 
        payload=payload, 
        stream_id=session.stream_id
    )

    return {
        "status": "accepted",
        "chat_id": chat_id,
        "stream_id": session.stream_id
    }

@router.get("/{chat_id}/stream/{stream_id}")
async def stream_chat(chat_id: str, stream_id: str, user_id: str = Depends(get_user_id_from_anywhere)):
    """
    SSE Endpoint for real-time token delivery.
    Consumes from the queue managed by StreamManager.
    """
    session = await stream_manager.get_session(stream_id)
    if not session or session.chat_id != chat_id:
        # If the session is missing, it's likely already been handled and removed.
        # We return a 'done' event instead of an error to prevent the UI from showing 
        # "Stream expired" during rapid re-renders or browser retries.
        async def finished_generator():
            yield json.dumps({"event": "done"})
        return EventSourceResponse(finished_generator())

    async def event_generator():
        last_index = 0
        try:
            while True:
                if session.interrupted.is_set():
                    yield json.dumps({"event": "error", "message": "Interrupted by user"})
                    break
                
                # Fetch any items after our last seen index
                new_items, current_len = await session.get_items_after(last_index)
                if not new_items:
                    # If no items and session is finished/interrupted, we're done
                    if session.finished.is_set() or session.interrupted.is_set():
                        break
                    continue # Should not happen with wait logic
                
                for item in new_items:
                    yield json.dumps(item)
                    if item["event"] == "done":
                        return # Connection finished naturally
                
                last_index = current_len

        except Exception as e:
            logger.error(f"SSE Generator Error: {e}")
        finally:
            # We don't remove immediately to allow for retries.
            # StreamManager cleanup logic should be added if memory becomes an issue.
            pass

    return EventSourceResponse(event_generator(), ping=20)

@router.get("/{chat_id}/placeholder")
async def stream_placeholder(
    chat_id: str, 
    mode: str = "chat",
    user_id: str = Depends(get_user_id_from_anywhere)
):
    from app.services.placeholder import get_personalized_placeholder
    from app.documents.user import UserDocument
    
    async def placeholder_generator():
        user = await UserDocument.find_by_id_or_uuid(user_id)
        
        # Fetch the full text and yield it once
        text = await get_personalized_placeholder(user, mode)
        yield json.dumps({"event": "placeholder_token", "text": text})
        
        # Signal completion
        yield json.dumps({"event": "placeholder_done"})

    return EventSourceResponse(placeholder_generator())

async def process_and_stream(chat_id: str, user_id: str, payload: ChatMessageRequest, stream_id: str):
    """
    Heavy lifting: Intent detection, context gathering, and LLM streaming.
    Pushes chunks to the stream session queue.
    """
    session = await stream_manager.get_session(stream_id)
    if not session: return

    try:
        # 1. SETUP & CONTEXT
        chat = await ChatSession.get(chat_id)
        msg_lower = (payload.message or "").lower()
        mode = payload.mode or "chat"

        async def save_ai_msg(content: str, **kwargs):
            """Persist an AI message to the DB — called before every early return."""
            ai = ChatMessage(sender_id="ai_system", content=content, **kwargs)
            chat.messages.append(ai)
            chat.updated_at = datetime.datetime.utcnow()
            await chat.save()

        INTENT_PATTERNS = {
            "recommendation_request": r"(recommend|suggest|what should i|what to|hungry|bored|watch|eat|listen|read)",
            "review_request": r"(review|write about|what do you think|rate this|opinion on)",
            "share_social_link": r"(https?://\S+|github\.com/\S+|linkedin\.com/\S+|twitter\.com/\S+|x\.com/\S+)",
            "greeting": r"^(hi|hello|hey|how far|good morning|good afternoon|good evening)",
            "onboarding_social": r"(my social|my github|my linkedin)"
        }
        
        detected_intent = "general_chat"
        if mode == "recommend": detected_intent = "recommendation_request"
        elif mode == "review": detected_intent = "review_request"
        else:
            for intent, pattern in INTENT_PATTERNS.items():
                if re.search(pattern, msg_lower):
                    detected_intent = intent; break
        
        # 1c. AUTO-SWITCH LOGIC: If user said "yes" to a mode suggestion
        last_ai_msg = next((m for m in reversed(chat.messages) if m.sender_id == "ai_system"), None)
        YES_WORDS = {"yes", "sure", "yep", "do it", "ok", "okay", "yeah", "go ahead", "switch", "switch it", "let's do it"}
        if last_ai_msg and msg_lower.strip() in YES_WORDS:
            # Detect which mode was being suggested from the last AI message
            last_lower = last_ai_msg.content.lower()
            if "recommendation mode" in last_lower:
                suggested_mode = "recommend"
            elif "review mode" in last_lower:
                suggested_mode = "review"
            else:
                suggested_mode = None

            if suggested_mode:
                await session.push("control", {"action": "switch_mode", "mode": suggested_mode})
                content = f"Switching to **{suggested_mode.capitalize()} mode** now! Let me get you sorted 🚀"
                await session.push("token", {"content": content})
                await save_ai_msg(content)
                await session.push("done", {})
                return

        # 1d. CONTEXT ENFORCEMENT & MODE SUGGESTION
        if mode == "chat":
            if detected_intent == "recommendation_request":
                is_generic = len(msg_lower.split()) < 3 or msg_lower in ["recommend", "suggest something", "i'm bored"]
                suggest_text = (
                    "I'd love to give you some recommendations! Should I switch to **Recommendation mode** so I can ask a few smart questions and nail your taste?"
                    if is_generic else
                    "I see you're looking for recommendations. For the best experience, should I switch to **Recommendation mode** for you now?"
                )
                await session.push("token", {"content": suggest_text})
                await save_ai_msg(suggest_text)
                await session.push("done", {"_suggest_mode": "recommend"})
                return

            elif detected_intent == "review_request":
                content = "I can help you write a review! Should I switch to **Review mode** so I can craft it in your voice?"
                await session.push("token", {"content": content})
                await save_ai_msg(content)
                await session.push("done", {"_suggest_mode": "review"})
                return

        # 1e. SELECTIVE FEEDBACK: Only show status for heavy intents
        # (Individual reasoning steps are streamed inside each intent branch below)

        # Gather User Context
        from app.documents.user import UserDocument
        user = await UserDocument.find_by_id_or_uuid(user_id)
        # ... (context notes logic remains same) ...
        context_notes = [f"MODE: {mode}", f"INTENT: {detected_intent}"]
        if user:
            context_notes.append(f"User Name: {user.name}")
            if user.email: context_notes.append(f"Email: {user.email}")
            if user.verified_profiles:
                profiles_info = [p.platform for p in user.verified_profiles]
                context_notes.append(f"Verified Profiles: {', '.join(profiles_info)}")
            if user.taste_profile.interests:
                context_notes.append(f"Interests: {', '.join(user.taste_profile.interests)}")
            if user.taste_profile.personality_traits:
                context_notes.append(f"Traits: {', '.join(user.taste_profile.personality_traits)}")
            if user.taste_profile.writing_tone:
                context_notes.append(f"Preferred Tone: {user.taste_profile.writing_tone}")
            if user.taste_profile.nigerian_context:
                context_notes.append("Context: Nigerian cultural context enabled.")
            if user.style_fingerprint.top_phrases:
                context_notes.append(f"Common Phrases: {', '.join(user.style_fingerprint.top_phrases[:5])}")
            if user.style_fingerprint.favorite_entities:
                context_notes.append(f"Favorite Topics/Brands: {', '.join(user.style_fingerprint.favorite_entities[:5])}")
            if user.is_birthday_today():
                context_notes.append("IMPORTANT: Today is the user's birthday! Wish them a happy birthday warmly.")

        # Build chat history for context-aware background tasks (strictly limited to save tokens)
        history_text = ""
        for m in chat.messages[-6:-1]:  # exclude the last one (current payload)
            role = "AI" if m.sender_id == "ai_system" else "User"
            if not m.content.startswith("["):
                # Truncate each historical message to max 150 chars to avoid token flooding
                content = m.content[:150] + ("..." if len(m.content) > 150 else "")
                history_text += f"{role}: {content}\n"

        # 2. ACTIONS
        recommendations = []
        reasoning_chain = []
        review = None
        
        # Hardcoded Greetings for Initializations
        if payload.message in ["[System Initialization]", "[Birthday Initialization]"]:
            # ... (greeting logic remains same) ...
            name = user.name.split()[0] if user and user.name else "fam"
            if payload.message == "[Birthday Initialization]":
                greeting_content = f"Happy Birthday, {name}! 🎉 Wishing you an amazing day filled with joy and great vibes.\n\nSince it's your special day, do you want me to recommend a fun spot to celebrate, or are we just catching up?"
            else:
                greeting_content = f"How far, {name}? I'm Reko — tuned to your taste.\n\nUse the **mode picker** above the composer to switch:\n\n- ⚡ **Instant chat** for quick questions\n- 🧭 **Recommendations** — I'll ask a few smart questions\n- ✍️ **Review simulator** — I'll write a review in your voice"
            
            chunk_size = 5
            for i in range(0, len(greeting_content), chunk_size):
                await session.push("token", {"content": greeting_content[i:i+chunk_size]})
                await asyncio.sleep(0.01)
                
            ai_msg = ChatMessage(sender_id="ai_system", content=greeting_content)
            chat.messages.append(ai_msg)
            chat.updated_at = datetime.datetime.utcnow()
            await chat.save()
            await session.push("done", {"recommendations": [], "review": None, "has_analysis": False, "has_simulator": False})
            return

        if detected_intent == "recommendation_request":
            # Check for enough context if in recommend mode (skip for internal system messages)
            is_system_msg = payload.message.startswith("[")
            if mode == "recommend" and not is_system_msg and len(msg_lower.strip()) < 3:
                content = "I'm ready to help you find something great! What kind of things are you looking for? (e.g. 'good movies for a rainy day', 'restaurants in Lagos', 'new afrobeat hits')"
                await session.push("token", {"content": content})
                await save_ai_msg(content)
                await session.push("done", {})
                return

            # Real CoT reasoning steps will be streamed live via push_status below

            async def push_status(msg: str):
                await session.push("status", msg)

            from app.api.v1.endpoints.recommendations import get_recommendations, RecommendationRequest, ContextInput
            
            # Combine history with the current request so the CoT and vector search have context
            context_msg = payload.message
            if history_text:
                context_msg = f"Previous Chat Context:\n{history_text}\n\nCurrent Request: {payload.message}"
                
            rec_req = RecommendationRequest(context=ContextInput(message=context_msg))
            claims = {"user_id": user_id}
            if user: claims["email"] = user.email

            res = await get_recommendations(rec_req, token_claims=claims, on_status=push_status, hybrid_override=payload.hybrid)
            recommendations = res.get("items", [])
            reasoning_chain = res.get("reasoning_chain", [])

            await session.push("status", f"Found {len(recommendations)} match{'es' if len(recommendations) != 1 else ''}. Crafting your response...")
            await asyncio.sleep(0.2)
        
        elif detected_intent == "review_request":
            # Check for context (URL or item name)
            has_context = any(word in msg_lower for word in ["http", "www", ".com", ".net", ".org"]) or len(msg_lower.split()) > 2
            if not has_context:
                content = "To write a great review, I need to know what item or place you're reviewing. Could you provide a name, a link, or a short description?"
                await session.push("token", {"content": content})
                await save_ai_msg(content)
                await session.push("done", {})
                return

            review_steps = [
                "Parsing item details from your request...",
                "Loading your writing style fingerprint...",
                "Calibrating tone and vocabulary to match your voice...",
                "Generating personalised review...",
            ]
            for step in review_steps:
                await session.push("status", step)
                await asyncio.sleep(0.5)

            from app.ml.review_generator import ReviewGenerator
            from app.documents.review import ReviewDocument

            product_name = payload.message.replace("review", "").strip() or "item"
            product_info = {"name": product_name}

            try:
                # Pass chat history as search_context so the LLM remembers previous discussions
                review_raw = await ReviewGenerator().generate(user_id, product_info, search_context=history_text)

                rev_doc = ReviewDocument(
                    user_id=user_id,
                    product_name=product_name,
                    product_category="General",
                    generated_text=review_raw["review_text"],
                    predicted_rating=4.5,
                    confidence=review_raw["style_match_score"],
                    style_snapshot={
                        "markers": review_raw["used_nigerian_markers"],
                        "sentences": review_raw["sentence_count"]
                    }
                )
                await rev_doc.save()

                review = {
                    "product": rev_doc.product_name,
                    "review": rev_doc.generated_text,
                    "rating": 4,
                    "confidence": rev_doc.confidence,
                    "markers": rev_doc.style_snapshot.get("markers", [])
                }
            except Exception as e:
                logger.error(f"Review Generation Failed: {e}")
                review = None

        # 3. LLM STREAMING — intent-aware prompt engineering
        from litellm.exceptions import RateLimitError

        # Build context-appropriate system prompt
        is_heavy = detected_intent in ["recommendation_request", "review_request"] or mode != "chat"

        if is_heavy:
            sys_prompt = (
                f"You are Reko AI, a highly personalised recommendation and review assistant. "
                f"Mode: {mode}. Intent: {detected_intent}. User context: {context_notes}.\n\n"
                "You have already completed your analysis. Now write a concise, warm, personalised response that:\n"
                "- Acknowledges the user's request naturally\n"
                "- Briefly introduces the results (recommendations or review)\n"
                "- Does NOT repeat raw data — the UI cards show the details\n"
                "- Uses a confident, friendly Nigerian-aware tone\n"
                "- Keeps it under 3 short paragraphs"
            )
        else:
            # Instant mode — fast, direct, no fluff
            sys_prompt = (
                f"You are Reko AI, a smart and friendly assistant. "
                f"User context: {context_notes}.\n\n"
                "Answer the user directly and concisely. "
                "Do NOT add lengthy preambles. "
                "If it's a simple question, give a simple answer. "
                "If it's a greeting, greet back warmly. "
                "Max 2 short paragraphs unless detail is truly needed."
            )
        messages = [{"role": "system", "content": sys_prompt}]
        for m in chat.messages[-10:]:
            role = "assistant" if m.sender_id == "ai_system" else "user"
            messages.append({"role": role, "content": m.content})
        
        user_content = payload.message or "[Process]"
        if user_content == "[Contextual Mode Switch]":
            if mode == "recommend": user_content = "Based on what we've discussed, please give me some fresh recommendations."
            elif mode == "review": user_content = "Based on our conversation, please help me write a review for the item we discussed."
            else: user_content = "Let's continue our conversation."
        elif user_content == "[Start Flow]":
            if mode == "recommend": user_content = "I want some recommendations. Please ask me some questions to understand what I'm looking for."
            elif mode == "review": user_content = "I want to write a review. Please ask me what item I'd like to review and any details you need."
            else: user_content = "Hello! I'm ready to start."
        elif user_content == "[Flow Complete]":
            answers = payload.flow_answers or {}
            ans_str = ", ".join([f"{k}: {v}" for k, v in answers.items()])
            if mode == "recommend": user_content = f"I've answered your questions: {ans_str}. Now, please give me some tailored recommendations."
            elif mode == "review": user_content = f"I want you to simulate a review for me. Here are the details: {ans_str}. Please write it in my voice."
            else: user_content = f"I've finished the steps: {ans_str}."

        messages.append({"role": "user", "content": user_content})

        # Store AI message data — only saved to DB AFTER streaming completes
        ai_has_analysis = (detected_intent == "recommendation_request")
        ai_has_simulator = (detected_intent == "review_request")

        try:
            from app.core.llm import llm_service
            response = llm_service.get_streaming_completion(
                messages=messages,
                temperature=0.7
            )

            full_content = ""
            async for chunk in response:
                if session.interrupted.is_set():
                    logger.warning(f"Stream {stream_id} interrupted mid-flow.")
                    break

                token = chunk.choices[0].delta.content or ""
                if token:
                    full_content += token
                    await session.push("token", {"content": token})

            # 4. FINALIZATION — Save the AI message only once, after streaming is done
            ai_msg = ChatMessage(
                sender_id="ai_system",
                content=full_content,
                has_analysis=ai_has_analysis,
                has_simulator=ai_has_simulator,
                metadata={"recommendations": recommendations, "review": review, "reasoning_chain": reasoning_chain}
            )
            chat.messages.append(ai_msg)
            chat.updated_at = datetime.datetime.utcnow()

            # --- Auto-rename if first meaningful exchange and still using default ---
            if chat.name.lower() in ["new chat", "new conversation"] and len(chat.messages) >= 2:
                user_q = payload.message or chat.messages[0].content
                if user_q and not user_q.startswith("["):  # Skip internal system messages
                    words = user_q.split()[:5]
                    chat.name = " ".join(words) + ("..." if len(user_q.split()) > 5 else "")

            await chat.save()

            await session.push("done", {
                "recommendations": recommendations,
                "reasoning_chain": reasoning_chain,
                "review": review,
                "has_analysis": ai_has_analysis,
                "has_simulator": ai_has_simulator
            })

        except Exception as e:
            if isinstance(e, RateLimitError) or "quota" in str(e).lower():
                logger.error(f"LiteLLM Quota Error: {e}")
                error_msg = f"My AI credits (tokens) have temporarily run out. Please contact my human creator at {settings.SUPPORT_EMAIL} to top me up! 🚀"
                await session.push("token", {"content": error_msg})
                
                ai_msg = ChatMessage(sender_id="ai_system", content=error_msg)
                chat.messages.append(ai_msg)
                await chat.save()
                
                await session.push("done", {"recommendations": recommendations, "review": review})
            else:
                logger.error(f"LLM Streaming Error: {e}")
                await session.push("error", {"message": str(e)})
                await session.push("done", {})

    except Exception as e:
        logger.error(f"Processing Error: {e}")
        try:
            # Send specific error if we can, else generic
            msg = str(e) if "Quota" in str(e) else "My apologies, I hit a snag while processing that. Please try again."
            await session.push("error", {"message": msg})
            await session.push("done", {})
        except:
            pass # Session might be closed or interrupted
