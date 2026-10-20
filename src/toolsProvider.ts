import { tool, Tool, ToolsProviderController } from "@lmstudio/sdk";
import { browserOeffnen, DIASHOW_URL, serverSicherstellen } from "./server";

export async function toolsProvider(_ctl: ToolsProviderController) {
  const tools: Tool[] = [];

  tools.push(
    tool({
      name: "diashow_oeffnen",
      description:
        "Öffnet die Diavortrag-Seite im Browser. Dort gibt der Nutzer selbst das Thema ein, stellt die Länge " +
        "(5-30 Minuten) ein und startet den vertonten Diavortrag. Verwende dieses Werkzeug, wenn der Nutzer eine " +
        "Diashow bzw. einen Diavortrag sehen oder erstellen möchte. Erzeuge danach selbst KEINE Bilder, Musik oder " +
        "Sprachausgabe für den Vortrag – das macht die Seite.",
      parameters: {},
      implementation: async () => {
        if (!(await serverSicherstellen())) {
          return (
            "Der Diashow-Server ließ sich nicht starten. Details stehen in " +
            "%USERPROFILE%\\LMStudioLocalPlugins\\diashow-daten\\server.log."
          );
        }
        browserOeffnen();
        return `Die Diavortrag-Seite ist im Browser geöffnet (${DIASHOW_URL}). Dort Thema eingeben, Länge wählen und „Projektor einschalten“.`;
      },
    }),
  );

  return tools;
}
