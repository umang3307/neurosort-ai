import streamlit as st
import google.generativeai as genai
import json

# --- 1. DEFINE AGENT SKILLS (NeuroSort Core Routers) ---
def route_to_do_now(task: str, urgency_reason: str) -> str:
    """Use for critical, time-sensitive tasks that require immediate execution."""
    return f"🚀 [CRITICAL] {task} | Reason: {urgency_reason}"

def route_to_schedule(task: str, suggested_timeframe: str) -> str:
    """Use for high-value strategic tasks that must be planned for later."""
    return f"📅 [SCHEDULED] {task} | Timeframe: {suggested_timeframe}"

def route_to_delegate(task: str, suggested_role: str) -> str:
    """Use for operational tasks that should be handed off to someone else or automated."""
    return f"🤝 [DELEGATED] {task} | Target Role: {suggested_role}"

def route_to_delete(task: str, elimination_justification: str) -> str:
    """Use for anxieties, non-actionable clutter, or low-value distractions."""
    return f"🗑️ [ELIMINATED] {task} | Justification: {elimination_justification}"

# --- 2. ADVANCED UI CONFIGURATION ---
st.set_page_config(
    page_title="NeuroSort AI - Cognitive Triage Agent", 
    page_icon="🧠", 
    layout="wide"
)

st.title("🧠 NeuroSort AI")
st.subheader("Advanced Cognitive Triage & Autonomous Task Distillation")
st.write("An intelligent concierge agent designed to ingest unstructured, chaotic mental streams and systematically map them to actionable execution matrix nodes using native tool routing.")

# Sidebar for configuration
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Gemini API Key:", type="password")
    st.markdown("---")
    st.markdown("### Agent Profile")
    st.info("**Model:** gemini-1.5-flash\n\n**Architecture:** Function-Driven Tool Routing\n\n**Domain:** Cognitive Productivity")

# Main Interface Layout
user_input = st.text_area(
    "Unload your thoughts, tasks, and anxieties here:", 
    placeholder="Example: I'm completely overwhelmed. The Q3 financial report is due to investors tomorrow morning and I haven't finished the summary. I also need to buy groceries tonight. I keep stressing about booking flights for a vacation in three months, and my team keeps asking me to review their code but I don't have time...",
    height=180
)

# --- 3. AGENT ORCHESTRATION ---
if st.button("Initialize Cognitive Triage") and api_key and user_input:
    genai.configure(api_key=api_key)
    
    # Registering the toolset
    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        tools=[route_to_do_now, route_to_schedule, route_to_delegate, route_to_delete]
    )
    
    with st.spinner("🧠 NeuroSort Agent is analyzing cognitive patterns and mapping execution paths..."):
        try:
            # Open an explicit chat session with automatic tool execution enabled
            chat = model.start_chat(enable_automatic_function_calling=True)
            
            system_orchestrator_prompt = f"""
            You are NeuroSort AI, an advanced cognitive triage agent specializing in decompression and task automation.
            Analyze the following unstructured user stream-of-consciousness data:
            
            "{user_input}"
            
            CRITICAL OBJECTIVES:
            1. Parse the text completely. Identify every single unique hidden task, stressor, or objective.
            2. For each identified item, invoke the most appropriate routing tool from your toolkit (`route_to_do_now`, `route_to_schedule`, `route_to_delegate`, `route_to_delete`). Do not skip any item.
            3. Once all tools have successfully executed, provide a masterful executive analysis report summarizing the triage strategy. Give a calculated 'Cognitive Load Index Score' out of 100 based on the complexity and volume of the input text, and provide brief, highly actionable advice for the user's focus.
            """
            
            response = chat.send_message(system_orchestrator_prompt)
            
            # Display Results in a beautiful, structured presentation
            st.success("Triage Protocol Complete.")
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown("### 📊 Executive Focus & Analysis")
                st.write(response.text)
                
            with col2:
                st.markdown("### 🛠️ Execution Trace Log")
                st.caption("This shows the chronological tool invocations handled autonomously by the agent.")
                
                # Extract and display the tool calls from the chat history to show the judges the tech works
                tool_calls_found = False
                for event in chat.history:
                    for part in event.parts:
                        if part.function_call:
                            tool_calls_found = True
                            st.code(f"Tool Triggered: {part.function_call.name}\nArgs: {json.dumps(dict(part.function_call.args), indent=2)}")
                
                if not tool_calls_found:
                    st.warning("No discrete tools were triggered. Try giving a mix of urgent tasks, long-term plans, and clear distractions.")
                    
        except Exception as e:
            st.error(f"An error occurred during runtime: {str(e)}")
            st.info("Verify your API key is correct and your input text contains clear actionable/non-actionable scenarios.")