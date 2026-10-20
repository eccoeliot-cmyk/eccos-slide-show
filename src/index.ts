import { PluginContext } from "@lmstudio/sdk";
import { toolsProvider } from "./toolsProvider";
import { serverSicherstellen } from "./server";

export async function main(context: PluginContext) {
  context.withToolsProvider(toolsProvider);
  // Nicht abwarten: LM Studio soll das Plugin sofort fertig geladen sehen.
  void serverSicherstellen();
}
