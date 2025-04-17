from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from dotenv import load_dotenv
import os

load_dotenv()

# Get API key from environment or set it explicitly
api_key = os.getenv("ANTHROPIC_API_KEY")
    # You could hardcode it here, but it's not recommended for security reasons


fetch_server = MCPServerStdio('python', ["-m", "mcp_server_fetch"])

# Create provider with explicit API key

agent = Agent(model= AnthropicModel(
    'claude-3-5-sonnet-latest',provider=AnthropicProvider(api_key='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')
),
              instrument=True,
              mcp_servers=[fetch_server])

async def main():
    async with agent.run_mcp_servers():
        result = await agent.run("hello!")
        while True:
            print(f"\n{result.data}")
            user_input = input("\n> ")
            result = await agent.run(user_input,
                                     message_history=result.new_messages())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())