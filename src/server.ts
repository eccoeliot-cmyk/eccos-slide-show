import { spawn } from "child_process";
import { createHash } from "crypto";
import { cpSync, existsSync, readdirSync, readFileSync, rmSync } from "fs";
import { request } from "http";
import { connect } from "net";
import { homedir } from "os";
import { dirname, join } from "path";

/**
 * Startet den Diashow-Server (vortrag/server.py, Python), sobald LM Studio das Plugin lädt – der Nutzer soll keinen
 * Server von Hand starten müssen.
 *
 * WICHTIG: LM Studio beendet Plugins ~20 s nach jeder Chat-Aktivität samt ihren Kindprozessen (Server-Protokoll
 * 2026-10-20 20:23:18: „Client disconnected“ – der Diashow-Server verschwand mitten in der Gliederung). Deshalb wird
 * der Server über WMI (Win32_Process.Create) als eigenständiger Prozess gestartet, der NICHT zum Prozessbaum des Plugins
 * gehört (dasselbe Vorgehen wie beim Autopiloten im Kriminalfall-Projekt). Er läuft dann weiter, bis Windows endet.
 *
 * Der Server läuft aus einer Kopie unter diashow-daten\programm\<Version>, nie aus dem Plugin-Ordner: ein laufender
 * Prozess sperrt seinen Ordner, und `lms dev --install` scheiterte daran mit EBUSY (2026-10-20, Plugin halb gelöscht).
 */
export const DIASHOW_PORT = 8430;
export const DIASHOW_URL = `http://127.0.0.1:${DIASHOW_PORT}`;

const PLUGINS = join(homedir(), "LMStudioLocalPlugins");
const PYTHON_KANDIDATEN = [join(PLUGINS, "mcp-servers", "venv", "Scripts", "python.exe"), "python"];
const PROGRAMM_DIR = join(PLUGINS, "diashow-daten", "programm");

/** vortrag/ in den Programmordner dieser Version kopieren (einmal je Version), dazu die eigene Musik („musik/“) und die
 * Saal-Geräusche („sounds/“) aus dem Plugin-Ordner. -> Ordner, aus dem der Server läuft */
function programmBereitstellen(ordner: string, version: string): string {
  const ziel = join(PROGRAMM_DIR, version);
  if (!existsSync(join(ziel, "server.py"))) {
    cpSync(join(ordner, "vortrag"), ziel, { recursive: true });
    for (const unter of ["musik", "sounds"]) {
      if (existsSync(join(ordner, unter))) {
        cpSync(join(ordner, unter), join(ziel, unter), { recursive: true });
      }
    }
  }
  return ziel;
}

/** Namen der Musik- bzw. Geräuschdateien – gehen in die Version ein, damit Änderungen nach einer Neuinstallation
 * ankommen. */
export function musikNamen(ordner: string): string {
  try {
    return readdirSync(ordner).filter((n) => /\.(mp3|wav|flac|ogg|m4a)$/i.test(n)).sort().join("\n");
  } catch {
    return "";
  }
}

/** Alte Programmversionen wegräumen – eine noch laufende (gesperrte) bleibt einfach liegen. */
function alteProgrammeLoeschen(version: string): void {
  try {
    for (const name of readdirSync(PROGRAMM_DIR)) {
      if (name === version) continue;
      try {
        rmSync(join(PROGRAMM_DIR, name), { recursive: true, force: true });
      } catch {
        // gesperrt – beim nächsten Mal
      }
    }
  } catch {
    // Ordner fehlt – nichts zu tun
  }
}

let startVersuch: Promise<boolean> | null = null;

export function portOffen(port = DIASHOW_PORT, timeoutMs = 800): Promise<boolean> {
  return new Promise((fertig) => {
    const s = connect({ host: "127.0.0.1", port });
    const ende = (ok: boolean) => {
      s.removeAllListeners();
      s.destroy();
      fertig(ok);
    };
    s.setTimeout(timeoutMs, () => ende(false));
    s.once("connect", () => ende(true));
    s.once("error", () => ende(false));
  });
}

function http(methode: "GET" | "POST", pfad: string, timeoutMs = 2500): Promise<any | null> {
  return new Promise((fertig) => {
    const req = request(
      { host: "127.0.0.1", port: DIASHOW_PORT, path: pfad, method: methode, timeout: timeoutMs,
        headers: methode === "POST" ? { "Content-Type": "application/json", "Content-Length": 2 } : {} },
      (res) => {
        let daten = "";
        res.setEncoding("utf8");
        res.on("data", (d) => (daten += d));
        res.on("end", () => {
          try {
            fertig(JSON.parse(daten));
          } catch {
            fertig(null);
          }
        });
      },
    );
    req.on("timeout", () => req.destroy());
    req.on("error", () => fertig(null));
    if (methode === "POST") req.write("{}");
    req.end();
  });
}

/** Ordner, in dem vortrag/server.py liegt (installiert läuft das Plugin gebündelt aus .lmstudio/). */
function pluginOrdner(): string | null {
  let d = __dirname;
  for (let i = 0; i < 5; i++) {
    if (existsSync(join(d, "vortrag", "server.py"))) return d;
    d = dirname(d);
  }
  return null;
}

/** Dieselbe Prüfsumme, die server.py als VERSION meldet. */
function eigeneVersion(ordner: string): string {
  const h = createHash("sha1");
  h.update(readFileSync(join(ordner, "vortrag", "server.py")));
  h.update(readFileSync(join(ordner, "vortrag", "web", "index.html")));
  h.update(musikNamen(join(ordner, "musik")) + "|" + musikNamen(join(ordner, "sounds")));
  return h.digest("hex").slice(0, 12);
}

function befehlszeile(teile: string[]): string {
  return teile.map((t) => (/[\s"]/.test(t) ? `"${t.replace(/"/g, '\\"')}"` : t)).join(" ");
}

/** Start über WMI – außerhalb des Prozessbaums von LM Studio. true, wenn Windows den Prozess angelegt hat. */
function wmiStarten(cmd: string[], cwd: string): Promise<boolean> {
  const psq = (s: string) => "'" + s.replace(/'/g, "''") + "'";
  const ps =
    "$ProgressPreference='SilentlyContinue'; " +
    "$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}; " +
    `$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=${psq(befehlszeile(cmd))}; ` +
    `CurrentDirectory=${psq(cwd)}; ProcessStartupInformation=$si}; Write-Output "$($r.ReturnValue) $($r.ProcessId)"`;
  return new Promise((fertig) => {
    let aus = "";
    const kind = spawn(
      "powershell",
      ["-NoProfile", "-NonInteractive", "-EncodedCommand", Buffer.from(ps, "utf16le").toString("base64")],
      { windowsHide: true, stdio: ["ignore", "pipe", "ignore"] },
    );
    const uhr = setTimeout(() => kind.kill(), 40000);
    kind.stdout.on("data", (d) => (aus += d.toString()));
    kind.on("error", () => fertig(false));
    kind.on("close", () => {
      clearTimeout(uhr);
      const teile = aus.trim().split(/\s+/);
      fertig(teile.length >= 2 && teile[teile.length - 2] === "0");
    });
  });
}

/** Rückfall, falls WMI gesperrt ist: losgelöst starten (kann dann mit dem Plugin enden). */
function losgeloestStarten(cmd: string[], cwd: string): boolean {
  try {
    const kind = spawn(cmd[0], cmd.slice(1), { cwd, stdio: "ignore", windowsHide: true, detached: true });
    kind.on("error", (err) => console.error(`[diashow-vortrag] Server-Start fehlgeschlagen: ${err.message}`));
    kind.unref();
    return true;
  } catch (err) {
    console.error(`[diashow-vortrag] Server-Start fehlgeschlagen: ${(err as Error).message}`);
    return false;
  }
}

async function warten(bedingung: () => Promise<boolean>, sekunden: number): Promise<boolean> {
  for (let i = 0; i < sekunden * 4; i++) {
    if (await bedingung()) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

async function starten(): Promise<boolean> {
  const ordner = pluginOrdner();
  if (!ordner) {
    console.error("[diashow-vortrag] vortrag/server.py nicht gefunden.");
    return false;
  }
  const version = eigeneVersion(ordner);
  if (await portOffen()) {
    const st = await http("GET", "/api/status?kurz=1");
    if (!st || st.version === version || st.vortrag_laeuft) return true;   // aktuell – oder erst nach dem Vortrag tauschen
    console.log(`[diashow-vortrag] ersetze Server-Version ${st.version} durch ${version}`);
    await http("POST", "/api/ende");
    if (!(await warten(async () => !(await portOffen()), 10))) return true;   // alter Server bleibt – besser als keiner
  }
  const python = PYTHON_KANDIDATEN.find((p) => p === "python" || existsSync(p))!;
  let cwd: string;
  try {
    cwd = programmBereitstellen(ordner, version);
  } catch (err) {
    console.error(`[diashow-vortrag] Programmkopie fehlgeschlagen (${(err as Error).message}) – starte aus dem Plugin-Ordner.`);
    cwd = join(ordner, "vortrag");
  }
  const cmd = [python, join(cwd, "server.py"), "--hintergrund"];
  if (!(await wmiStarten(cmd, cwd))) {
    console.error("[diashow-vortrag] Start über WMI nicht möglich – starte losgelöst.");
    losgeloestStarten(cmd, cwd);
  }
  const ok = await warten(() => portOffen(), 20);
  if (ok) alteProgrammeLoeschen(version);
  return ok;
}

/** Startet den Server höchstens einmal gleichzeitig; true, sobald er erreichbar ist. */
export function serverSicherstellen(): Promise<boolean> {
  if (!startVersuch) {
    startVersuch = starten().finally(() => {
      startVersuch = null;
    });
  }
  return startVersuch;
}

/** Öffnet die Diashow-Seite im Standardbrowser. */
export function browserOeffnen(): void {
  const kind = spawn("cmd", ["/c", "start", "", DIASHOW_URL], { stdio: "ignore", windowsHide: true, detached: true });
  kind.on("error", () => {});
  kind.unref();
}
