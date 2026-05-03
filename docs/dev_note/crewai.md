How CrewAI Divides Prompts by Default

CrewAI uses a system of "prompt slices" to construct the final prompts sent to the LLM. The way information is divided depends on whether you are using the default settings or have chosen to customize the templates.

1. The Default Behavior (System vs. User)

In its default configuration, CrewAI crafts the prompts as follows:

System Prompt: This is where CrewAI places its core behavioral instructions. These are not your agent's role and goal, but rather hard-coded formatting rules designed to ensure the agent acts reliably. The content of this prompt changes based on the agent's capabilities .

For Agents Without Tools: The system prompt includes strict formatting instructions like "I MUST use these formats, my job depends on it!".
For Agents With Tools: The system prompt provides a specific template for the agent to follow, including sections for Thought, Action, Action Input, and Observation.
For Structured Outputs: The system prompt will instruct the agent to format its final answer according to a specific Pydantic or JSON model.

User Prompt: The user prompt is where the vast majority of your specific configuration is placed. This includes your agent's role, goal, and backstory, as well as the task's description and expected_output .
This means that by default, both the agent's persona and the task's instructions are sent to the LLM as part of the user prompt, while the system prompt is reserved for CrewAI's internal formatting rules.

# Default system prompt template (simplified):
"You are {role}. {backstory}\nYour personal goal is: {goal}\n..."

# Default task prompt template:
"Current Task: {input}\nBegin! This is VERY important to you..."