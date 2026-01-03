import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

async function askCloudflare() {
  // 1. Parse the query from the command line arguments
  const query = process.argv[2];
  if (!query) {
    console.error("\n❌ Usage: pnpm exec tsx scripts/ask-cloudflare.ts \"Your question here\"");
    process.exit(1);
  }

  console.log(`\n🔍 Asking Cloudflare Docs: "${query}"...`);

  // 2. Configure the Transport to use 'npx' (or 'pnpm dlx') to run the remote MCP server
  const transport = new StdioClientTransport({
    command: "npx",
    args: ["-y", "mcp-remote", "https://docs.mcp.cloudflare.com/mcp"],
  });

  const client = new Client(
    { name: "jules-docs-client", version: "1.0.0" },
    { capabilities: {} }
  );

  try {
    await client.connect(transport);
    
    // 3. Find the 'ask' or 'search' tool
    const tools = await client.listTools();
    const toolName = tools.tools.find(t => t.name === "ask" || t.name === "search")?.name;

    if (!toolName) {
        throw new Error("Could not find a search tool on the Cloudflare MCP server.");
    }

    // 4. Execute the query
    const result = await client.callTool({
      name: toolName,
      arguments: { question: query, query: query },
    });

    // 5. Parse and display the result
    // @ts-ignore
    const answer = result.content.find(c => c.type === "text")?.text;
    
    console.log("\n--- 💡 Cloudflare Docs Answer ---\n");
    console.log(answer || "No answer found.");
    console.log("\n-------------------------------\n");

  } catch (error) {
    console.error("\n❌ Error querying Cloudflare docs:", error);
  } finally {
    process.exit(0);
  }
}

askCloudflare();
