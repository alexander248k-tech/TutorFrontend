import html
import importlib
import os
import re
import shutil
import subprocess
import sys
import platform
import json
import time
import functools
import http.server
import socketserver
import webbrowser

IS_WIN = platform.system() == "Windows"

# ---------------------------------------------------------------------------
# Rutas (relativas a donde está este script, funciona desde cualquier carpeta)
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Si el script está dentro del proyecto Ionic, se usa esa carpeta;
# si no, se busca la subcarpeta "mi-app-ionic".
if os.path.exists(os.path.join(SCRIPT_DIR, "package.json")):
    PROJECT_DIR = SCRIPT_DIR
else:
    PROJECT_DIR = os.path.join(SCRIPT_DIR, "mi-app-ionic")

ANDROID_DIR = os.path.join(PROJECT_DIR, "android")
DESKTOP_DIR = os.path.join(PROJECT_DIR, "desktop")

# Las carpetas de builds quedan junto a la carpeta del proyecto
BUILDS_DIR = os.path.join(os.path.dirname(PROJECT_DIR), "builds")
WEB_BUILD_DIR = os.path.join(BUILDS_DIR, "web")
APK_BUILD_DIR = os.path.join(BUILDS_DIR, "apk")
EXE_BUILD_DIR = os.path.join(BUILDS_DIR, "exe")
LINUX_BUILD_DIR = os.path.join(BUILDS_DIR, "linux")

# SDK de Android: variable de entorno o ruta por defecto del usuario actual
ANDROID_SDK_PATH = (
    os.environ.get("ANDROID_HOME")
    or os.environ.get("ANDROID_SDK_ROOT")
    or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
)
ADB_PATH = os.path.join(ANDROID_SDK_PATH, "platform-tools", "adb.exe" if IS_WIN else "adb")
GRADLEW_CMD = "gradlew.bat" if IS_WIN else "./gradlew"

# Capacitor 8 requiere Java 21. Java 26 NO es compatible con Gradle todavía.
MIN_JAVA = 21
MAX_JAVA = 24

# Archivos del proyecto que se modifican con la configuración
CAP_TS = os.path.join(PROJECT_DIR, "capacitor.config.ts")
CAP_JSON = os.path.join(PROJECT_DIR, "capacitor.config.json")
INDEX_HTML = os.path.join(PROJECT_DIR, "src", "index.html")

# Archivos propios del script (configuración e icono guardados)
CONFIG_FILE = os.path.join(SCRIPT_DIR, "build_config.json")
ASSETS_DIR = os.path.join(SCRIPT_DIR, "build_assets")
ICON_STORE = os.path.join(ASSETS_DIR, "icon.png")


# ---------------------------------------------------------------------------
# Configuración (nombre, paquete, versión, icono)
# ---------------------------------------------------------------------------
CONFIG_DEFECTO = {
    "appId": "",
    "appName": "",
    "version": "1.0.0",
    "icon": "",
    "exe_embed_icon": False,
}


def leer_capacitor():
    """Lee appId y appName actuales de capacitor.config.ts / .json."""
    datos = {}
    try:
        if os.path.exists(CAP_TS):
            with open(CAP_TS, "r", encoding="utf-8") as f:
                txt = f.read()
            for clave in ("appId", "appName"):
                m = re.search(clave + r"""\s*:\s*['"]([^'"]*)['"]""", txt)
                if m:
                    datos[clave] = m.group(1)
        elif os.path.exists(CAP_JSON):
            with open(CAP_JSON, "r", encoding="utf-8") as f:
                j = json.load(f)
            for clave in ("appId", "appName"):
                if clave in j:
                    datos[clave] = j[clave]
    except Exception:
        pass
    return datos


def cargar_config():
    cfg = dict(CONFIG_DEFECTO)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            print("⚠️ build_config.json está dañado, se usan valores por defecto.")
    cap = leer_capacitor()
    if not cfg["appId"]:
        cfg["appId"] = cap.get("appId", "com.ejemplo.miapp")
    if not cfg["appName"]:
        cfg["appName"] = cap.get("appName", "MiApp")
    return cfg


def guardar_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def slug(texto):
    s = re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")
    return s or "mi-app"


def version_code(version):
    """1.2.3 -> 10203 (para versionCode de Android)."""
    partes = [int(p) for p in version.split(".")[:3]]
    while len(partes) < 3:
        partes.append(0)
    return partes[0] * 10000 + partes[1] * 100 + partes[2]


def valida_app_id(texto):
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$", texto))


def valida_version(texto):
    return bool(re.match(r"^\d{1,3}\.\d{1,2}\.\d{1,2}$", texto))


# ---- Pillow / iconos ------------------------------------------------------
def asegurar_pillow():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        print("📦 Instalando Pillow para procesar el icono (una sola vez)...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "pillow"])
        if r.returncode != 0:
            return False
        importlib.invalidate_caches()
        try:
            import PIL  # noqa: F401,F811
            return True
        except ImportError:
            return False


def cargar_icono(cfg):
    """Devuelve la imagen (PIL, RGBA, cuadrada) configurada, o None."""
    ruta = cfg.get("icon", "")
    if not ruta or not os.path.exists(ruta):
        return None
    if not asegurar_pillow():
        print("⚠️ No se pudo instalar Pillow: se omite el icono.")
        return None
    from PIL import Image
    return Image.open(ruta).convert("RGBA")


DENSIDADES_ANDROID = {
    # densidad: (icono clásico, icono adaptativo)
    "mdpi": (48, 108),
    "hdpi": (72, 162),
    "xhdpi": (96, 216),
    "xxhdpi": (144, 324),
    "xxxhdpi": (192, 432),
}


def aplicar_icono_android(img):
    from PIL import Image, ImageDraw
    res = os.path.join(ANDROID_DIR, "app", "src", "main", "res")
    lanczos = Image.LANCZOS

    for dens, (clasico, adaptativo) in DENSIDADES_ANDROID.items():
        carpeta = os.path.join(res, f"mipmap-{dens}")
        os.makedirs(carpeta, exist_ok=True)

        cuadrado = img.resize((clasico, clasico), lanczos)
        cuadrado.save(os.path.join(carpeta, "ic_launcher.png"))

        mascara = Image.new("L", (clasico, clasico), 0)
        ImageDraw.Draw(mascara).ellipse((0, 0, clasico - 1, clasico - 1), fill=255)
        redondo = Image.new("RGBA", (clasico, clasico), (0, 0, 0, 0))
        redondo.paste(cuadrado, (0, 0), mascara)
        redondo.save(os.path.join(carpeta, "ic_launcher_round.png"))

        # Primer plano adaptativo: icono al 70% centrado sobre lienzo transparente
        interior = int(adaptativo * 0.70)
        lienzo = Image.new("RGBA", (adaptativo, adaptativo), (0, 0, 0, 0))
        pequeno = img.resize((interior, interior), lanczos)
        margen = (adaptativo - interior) // 2
        lienzo.paste(pequeno, (margen, margen), pequeno)
        lienzo.save(os.path.join(carpeta, "ic_launcher_foreground.png"))

    # Fondo adaptativo: color de la esquina del icono (blanco si es transparente)
    px = img.getpixel((0, 0))
    r, g, b = (255, 255, 255) if px[3] < 128 else px[:3]
    valores = os.path.join(res, "values")
    os.makedirs(valores, exist_ok=True)
    with open(os.path.join(valores, "ic_launcher_background.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                f'    <color name="ic_launcher_background">#{r:02X}{g:02X}{b:02X}</color>\n'
                '</resources>\n')
    print("🎨 Iconos de Android generados.")


def aplicar_favicon(img):
    carpeta = os.path.join(PROJECT_DIR, "src", "assets", "icon")
    if os.path.isdir(carpeta):
        from PIL import Image
        img.resize((192, 192), Image.LANCZOS).save(os.path.join(carpeta, "favicon.png"))
        print("🎨 Favicon web actualizado.")


# ---- Aplicar la configuración a los archivos del proyecto -----------------
def _reemplazar_ts(txt, clave, valor):
    def rep(m):
        q = m.group(2)
        v = valor.replace("\\", "\\\\").replace(q, "\\" + q)
        return f"{m.group(1)}{q}{v}{q}"
    patron = r"(" + clave + r"""\s*:\s*)(['"])[^'"]*\2"""
    return re.sub(patron, rep, txt, count=1)


def aplicar_config_capacitor(cfg):
    try:
        if os.path.exists(CAP_TS):
            with open(CAP_TS, "r", encoding="utf-8") as f:
                txt = f.read()
            nuevo = _reemplazar_ts(txt, "appId", cfg["appId"])
            nuevo = _reemplazar_ts(nuevo, "appName", cfg["appName"])
            if nuevo != txt:
                with open(CAP_TS, "w", encoding="utf-8") as f:
                    f.write(nuevo)
                print("📝 capacitor.config.ts actualizado.")
        elif os.path.exists(CAP_JSON):
            with open(CAP_JSON, "r", encoding="utf-8") as f:
                j = json.load(f)
            j["appId"], j["appName"] = cfg["appId"], cfg["appName"]
            with open(CAP_JSON, "w", encoding="utf-8") as f:
                json.dump(j, f, indent=2, ensure_ascii=False)
            print("📝 capacitor.config.json actualizado.")
        else:
            print("⚠️ No se encontró capacitor.config.ts/json.")
    except Exception as e:
        print(f"⚠️ No se pudo actualizar la config de Capacitor: {e}")


def aplicar_titulo_web(cfg):
    if not os.path.exists(INDEX_HTML):
        return
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        txt = f.read()
    titulo = html.escape(cfg["appName"], quote=False)
    nuevo = re.sub(r"<title>.*?</title>", lambda m: f"<title>{titulo}</title>",
                   txt, count=1, flags=re.S)
    if nuevo != txt:
        with open(INDEX_HTML, "w", encoding="utf-8") as f:
            f.write(nuevo)
        print("📝 Título de index.html actualizado.")


def aplicar_config_android(cfg, img):
    """Cambia applicationId, versión, nombre e iconos del proyecto Android.
    El 'namespace' (paquete interno del código) se deja como está a propósito."""
    gradle = os.path.join(ANDROID_DIR, "app", "build.gradle")
    if os.path.exists(gradle):
        with open(gradle, "r", encoding="utf-8") as f:
            txt = f.read()
        txt, n1 = re.subn(r"""(applicationId\s*=?\s*)["'][^"']*["']""",
                          lambda m: f'{m.group(1)}"{cfg["appId"]}"', txt, count=1)
        txt, n2 = re.subn(r"(versionCode\s*=?\s*)\d+",
                          lambda m: f"{m.group(1)}{version_code(cfg['version'])}", txt, count=1)
        txt, n3 = re.subn(r"""(versionName\s*=?\s*)["'][^"']*["']""",
                          lambda m: f'{m.group(1)}"{cfg["version"]}"', txt, count=1)
        with open(gradle, "w", encoding="utf-8") as f:
            f.write(txt)
        if not (n1 and n2 and n3):
            print("⚠️ No pude actualizar todos los campos de app/build.gradle "
                  f"(applicationId={bool(n1)}, versionCode={bool(n2)}, versionName={bool(n3)}).")
        else:
            print("📝 app/build.gradle actualizado (applicationId y versión).")

    strings = os.path.join(ANDROID_DIR, "app", "src", "main", "res", "values", "strings.xml")
    if os.path.exists(strings):
        with open(strings, "r", encoding="utf-8") as f:
            txt = f.read()
        nombre = html.escape(cfg["appName"], quote=False).replace("'", "\\'").replace('"', '\\"')
        for clave, valor in (("app_name", nombre), ("title_activity_main", nombre),
                             ("package_name", cfg["appId"]), ("custom_url_scheme", cfg["appId"])):
            txt = re.sub(r'(<string name="' + clave + r'">)[^<]*(</string>)',
                         lambda m, v=valor: m.group(1) + v + m.group(2), txt)
        with open(strings, "w", encoding="utf-8") as f:
            f.write(txt)
        print("📝 strings.xml actualizado (nombre de la app).")

    if img is not None:
        aplicar_icono_android(img)


def preparar_proyecto():
    """Aplica la configuración a los archivos web/Capacitor. Devuelve (cfg, icono)."""
    cfg = cargar_config()
    print(f"⚙️ Configuración: {cfg['appName']} | {cfg['appId']} | v{cfg['version']}"
          f" | icono: {'sí' if cfg['icon'] else 'no'}")
    aplicar_config_capacitor(cfg)
    aplicar_titulo_web(cfg)
    img = cargar_icono(cfg)
    if img is not None:
        aplicar_favicon(img)
    return cfg, img


# ---------------------------------------------------------------------------
# Proyecto Electron (escritorio)
# ---------------------------------------------------------------------------
ELECTRON_MAIN_JS = r"""const { app, BrowserWindow, protocol, net } = require('electron');
const path = require('path');
const fs = require('fs');
const { pathToFileURL } = require('url');

// Protocolo propio para que las rutas absolutas de Angular/Ionic funcionen
protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true } }
]);

function createWindow() {
  const iconPath = path.join(__dirname, 'icon.png');
  const win = new BrowserWindow({
    width: 1100,
    height: 800,
    autoHideMenuBar: true,
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    webPreferences: { contextIsolation: true }
  });
  win.loadURL('app://localhost/');
}

app.whenReady().then(() => {
  const root = path.join(__dirname, 'app');

  protocol.handle('app', (req) => {
    const url = new URL(req.url);
    let file = path.normalize(path.join(root, decodeURIComponent(url.pathname)));
    if (!file.startsWith(root)) return new Response('Forbidden', { status: 403 });
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      file = path.join(root, 'index.html'); // fallback para rutas de Angular
    }
    return net.fetch(pathToFileURL(file).toString());
  });

  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
"""


def escribir_proyecto_electron(cfg, img):
    """Genera main.js, package.json e iconos del proyecto Electron con la config actual."""
    os.makedirs(DESKTOP_DIR, exist_ok=True)
    nombre_bin = slug(cfg["appName"])

    with open(os.path.join(DESKTOP_DIR, "main.js"), "w", encoding="utf-8") as f:
        f.write(ELECTRON_MAIN_JS)

    tiene_icono = img is not None
    png = os.path.join(DESKTOP_DIR, "icon.png")
    ico = os.path.join(DESKTOP_DIR, "icon.ico")
    if tiene_icono:
        from PIL import Image
        img.resize((512, 512), Image.LANCZOS).save(png)
        img.resize((256, 256), Image.LANCZOS).save(
            ico, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        print("🎨 Iconos de escritorio generados.")
    else:
        for ruta in (png, ico):
            if os.path.exists(ruta):
                os.remove(ruta)

    win = {"target": "portable", "signAndEditExecutable": bool(cfg.get("exe_embed_icon"))}
    linux = {"target": "AppImage", "category": "Utility", "executableName": nombre_bin}
    if tiene_icono:
        win["icon"] = "icon.ico"
        linux["icon"] = "icon.png"

    paquete = {
        "name": nombre_bin,
        "version": cfg["version"],
        "description": f"Version de escritorio de {cfg['appName']}",
        "author": "Robakills",
        "main": "main.js",
        "devDependencies": {
            "electron": "^33.0.0",
            "electron-builder": "^25.1.8",
        },
        "build": {
            "appId": cfg["appId"],
            "productName": cfg["appName"],
            "directories": {"output": "dist"},
            "files": ["main.js", "app/**/*", "icon.png"],
            "win": win,
            "linux": linux,
        },
    }
    with open(os.path.join(DESKTOP_DIR, "package.json"), "w", encoding="utf-8") as f:
        json.dump(paquete, f, indent=2, ensure_ascii=False)



# ---------------------------------------------------------------------------
# Utilidades, Java, ADB, servidor web y WSL
# ---------------------------------------------------------------------------
def crear_carpetas_builds():
    for carpeta in [WEB_BUILD_DIR, APK_BUILD_DIR, EXE_BUILD_DIR, LINUX_BUILD_DIR]:
        os.makedirs(carpeta, exist_ok=True)


def run_command(command, cwd=None, env=None):
    print(f"\n[EJECUTANDO]: {command}")
    try:
        subprocess.run(command, shell=True, check=True, cwd=cwd, env=env)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR]: El comando falló con el código {e.returncode}")
        return False


def version_java(java_home):
    """Devuelve la versión mayor del JDK en java_home, o None."""
    exe = os.path.join(java_home, "bin", "java.exe" if IS_WIN else "java")
    if not os.path.exists(exe):
        return None
    try:
        r = subprocess.run([exe, "-version"], capture_output=True, text=True)
        m = re.search(r'version "(\d+)(?:\.(\d+))?', r.stderr + r.stdout)
        if not m:
            return None
        major = int(m.group(1))
        return int(m.group(2)) if major == 1 else major  # 1.8 -> 8
    except Exception:
        return None


def encontrar_java_valido():
    """Busca un JDK entre MIN_JAVA y MAX_JAVA, ignorando el Java 26 del sistema."""
    candidatas = [
        os.environ.get("JAVA_HOME", ""),
        r"C:\Program Files\Android\Android Studio\jbr",
        os.path.expanduser(r"~\AppData\Local\Programs\Android Studio\jbr"),
    ]
    bases = [
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Java",
        r"C:\Program Files\Microsoft",
        r"C:\Program Files\Amazon Corretto",
        r"C:\Program Files\Zulu",
    ]
    for base in bases:
        if os.path.isdir(base):
            candidatas += [os.path.join(base, d) for d in sorted(os.listdir(base), reverse=True)]

    for ruta in candidatas:
        if ruta and os.path.isdir(ruta):
            v = version_java(ruta)
            if v:
                print(f"   revisando {ruta} -> Java {v}")
            if v and MIN_JAVA <= v <= MAX_JAVA:
                print(f"🔧 Java {v} válido: {ruta}")
                return ruta
    return None


def carpeta_web_resultante():
    """Detecta dónde dejó los archivos el build (www o www/browser)."""
    base = os.path.join(PROJECT_DIR, "www")
    browser = os.path.join(base, "browser")
    if os.path.exists(os.path.join(browser, "index.html")):
        return browser
    if os.path.exists(os.path.join(base, "index.html")):
        return base
    return None


def configurar_gradle(java_path):
    """Escribe local.properties (SDK) y gradle.properties (JDK correcto)."""
    sdk = ANDROID_SDK_PATH.replace("\\", "/")
    with open(os.path.join(ANDROID_DIR, "local.properties"), "w", encoding="utf-8") as f:
        f.write(f"sdk.dir={sdk}\n")

    props = os.path.join(ANDROID_DIR, "gradle.properties")
    lineas = []
    if os.path.exists(props):
        with open(props, "r", encoding="utf-8") as f:
            lineas = [l for l in f.readlines() if not l.startswith("org.gradle.java.home")]
        if lineas and not lineas[-1].endswith("\n"):
            lineas[-1] += "\n"
    lineas.append(f"org.gradle.java.home={java_path.replace(chr(92), '/')}\n")
    with open(props, "w", encoding="utf-8") as f:
        f.writelines(lineas)
    print("📝 local.properties y gradle.properties actualizados")


def instalar_apk(apk_path):
    print("\n--- 📲 INSTALANDO APK ---")
    adb = ADB_PATH if os.path.exists(ADB_PATH) else shutil.which("adb")
    if not adb:
        print("⚠️ No se encontró adb.")
        return
    if not os.path.exists(apk_path):
        print("❌ El archivo APK no existe.")
        return

    out = subprocess.run([adb, "devices"], capture_output=True, text=True).stdout
    print(out)
    estados = [l.split("\t") for l in out.splitlines()[1:] if "\t" in l]
    listos = [s for s, e in estados if e.strip() == "device"]

    if listos:
        if run_command(f'"{adb}" -s {listos[0]} install -r "{apk_path}"'):
            print("🎉 ¡Aplicación instalada en tu celular!")
    elif estados:
        print(f"⚠️ Dispositivo en estado '{estados[0][1].strip()}'. Acepta la autorización de depuración USB en el celular.")
    else:
        print("⚠️ No hay dispositivos conectados con Depuración USB activa.")


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    """Servidor estático con fallback a index.html (rutas de Angular)."""

    def do_GET(self):
        sin_query = self.path.split("?")[0]
        ruta = self.translate_path(sin_query)
        if not os.path.exists(ruta) and "." not in os.path.basename(sin_query):
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, format, *args):
        pass  # sin ruido en consola


def correr_web():
    print("\n--- 🌐 CORRIENDO WEB ---")
    if not os.path.exists(os.path.join(WEB_BUILD_DIR, "index.html")):
        print("⚠️ No hay build web en builds/web. Primero usa la opción 2 del menú.")
        return

    handler = functools.partial(SPAHandler, directory=WEB_BUILD_DIR)
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    servidor = None
    for puerto in range(8080, 8091):
        try:
            servidor = socketserver.ThreadingTCPServer(("127.0.0.1", puerto), handler)
            break
        except OSError:
            continue
    if not servidor:
        print("❌ No hay puertos libres entre 8080 y 8090.")
        return

    url = f"http://localhost:{puerto}"
    print(f"✅ Sirviendo {os.path.abspath(WEB_BUILD_DIR)}")
    print(f"🌍 Abre: {url}")
    print("   Presiona Ctrl+C para detener el servidor y volver al menú.")
    webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Servidor detenido.")
    finally:
        servidor.server_close()


def correr_exe():
    print("\n--- 💻 CORRIENDO EJECUTABLE ---")
    patron = ".exe" if IS_WIN else ".AppImage"
    carpeta = EXE_BUILD_DIR if IS_WIN else LINUX_BUILD_DIR
    archivos = []
    if os.path.isdir(carpeta):
        archivos = [os.path.join(carpeta, f) for f in os.listdir(carpeta) if f.endswith(patron)]
    if not archivos:
        print(f"⚠️ No hay ningún {patron} en {carpeta}. Primero usa la opción 4 del menú.")
        return

    exe = max(archivos, key=os.path.getmtime)
    print(f"🚀 Abriendo: {exe}")
    try:
        if not IS_WIN:
            os.chmod(exe, 0o755)
        subprocess.Popen([exe], cwd=os.path.dirname(exe))
        print("✅ Aplicación lanzada (la ventana puede tardar unos segundos).")
    except Exception as e:
        print(f"❌ No se pudo abrir: {e}")


def obtener_adb():
    return ADB_PATH if os.path.exists(ADB_PATH) else shutil.which("adb")


def dispositivo_listo(adb):
    """Devuelve el id del primer dispositivo en estado 'device', o None (y explica por qué)."""
    out = subprocess.run([adb, "devices"], capture_output=True, text=True).stdout
    estados = [l.split("\t") for l in out.splitlines()[1:] if "\t" in l]
    listos = [s for s, e in estados if e.strip() == "device"]
    if listos:
        return listos[0]
    if estados:
        print(f"⚠️ Dispositivo en estado '{estados[0][1].strip()}'. Acepta la autorización de depuración USB en el celular.")
    else:
        print("⚠️ No hay celular conectado con Depuración USB activa.")
    return None


def adb_run(adb, args):
    """Ejecuta adb capturando la salida. Devuelve (código, texto)."""
    r = subprocess.run([adb] + args, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def ruta_a_wsl(ruta_windows):
    """C:\\a\\b -> /mnt/c/a/b"""
    ruta = os.path.abspath(ruta_windows)
    unidad, resto = os.path.splitdrive(ruta)
    return "/mnt/" + unidad.rstrip(":").lower() + resto.replace("\\", "/")


def distros_wsl():
    try:
        r = subprocess.run(["wsl", "-l", "-q"], capture_output=True)
    except FileNotFoundError:
        return None
    texto = r.stdout.decode("utf-16-le", errors="ignore").replace("\x00", "")
    nombres = [l.strip() for l in texto.splitlines() if l.strip()]
    return [n for n in nombres if not n.lower().startswith("docker-desktop")]


SCRIPT_WSL_DEPS = """#!/bin/bash
if ldconfig -p | grep -q libnss3 && ldconfig -p | grep -q libgbm && ldconfig -p | grep -q libgtk-3; then
  echo "Dependencias de Electron ya instaladas."
  exit 0
fi
echo "Instalando dependencias de Electron (una sola vez)..."
apt-get update
PKGS="libgtk-3-0 libnss3 libgbm1 libxss1 libxtst6 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libcups2"
apt-get install -y $PKGS
apt-get install -y libasound2t64 || apt-get install -y libasound2
"""


SCRIPT_WSL_RUN = """#!/bin/bash
rm -rf /tmp/miapp-linux
mkdir -p /tmp/miapp-linux
tar -xzf "$1" -C /tmp/miapp-linux || { echo "Error al extraer el tar.gz"; exit 1; }
# El directorio de la app es el que contiene libffmpeg.so (propio de Electron)
LIB=$(find /tmp/miapp-linux -name 'libffmpeg.so' | head -1)
if [ -z "$LIB" ]; then
  echo "No se encontro libffmpeg.so. Contenido extraido:"
  find /tmp/miapp-linux -maxdepth 3 | head -50
  exit 1
fi
DIR=$(dirname "$LIB")
# El binario es el archivo grande sin extension (no depende del bit de ejecucion)
BIN=$(find "$DIR" -maxdepth 1 -type f -size +30M ! -name '*.so*' ! -name '*.pak' ! -name '*.bin' ! -name '*.dat' | head -1)
if [ -z "$BIN" ]; then
  echo "No se encontro el binario en $DIR. Contenido:"
  ls -la "$DIR"
  exit 1
fi
chmod +x "$BIN" 2>/dev/null
chmod +x "$DIR/chrome-sandbox" 2>/dev/null
echo "Ejecutando: $BIN"
cd "$DIR"
exec "$BIN" --no-sandbox --disable-gpu
"""


def correr_linux_wsl():
    print("\n--- 🐧 PROBANDO LINUX EN WSL ---")
    if not IS_WIN:
        print("ℹ️ Ya estás en Linux: usa la opción 2 (ejecutable) para abrir el AppImage.")
        return False

    tars = []
    if os.path.isdir(LINUX_BUILD_DIR):
        tars = [os.path.join(LINUX_BUILD_DIR, f) for f in os.listdir(LINUX_BUILD_DIR) if f.endswith(".tar.gz")]
    if not tars:
        print("⚠️ No hay .tar.gz en builds/linux. Primero usa la opción 4 del menú.")
        return False
    tar = max(tars, key=os.path.getmtime)

    distros = distros_wsl()
    if distros is None:
        print("⚠️ WSL no está instalado. Es la forma más ligera de probar Linux en Windows (sin VM completa).")
        print("   Instálalo con PowerShell como administrador:  wsl --install -d Ubuntu")
        print("   Reinicia el PC, crea tu usuario de Ubuntu y vuelve a intentar.")
        return False
    if not distros:
        print("⚠️ WSL está instalado pero sin distribución. Ejecuta (PowerShell como administrador):")
        print("   wsl --install -d Ubuntu")
        return False

    distro = distros[0]
    print(f"🐧 Usando la distribución: {distro}")

    os.makedirs(BUILDS_DIR, exist_ok=True)
    deps = os.path.join(BUILDS_DIR, "_wsl_deps.sh")
    run = os.path.join(BUILDS_DIR, "_wsl_run.sh")
    for ruta, contenido in ((deps, SCRIPT_WSL_DEPS), (run, SCRIPT_WSL_RUN)):
        with open(ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenido)

    # Comprobar que la distribución ya terminó su configuración inicial
    prueba = subprocess.run(["wsl", "-d", distro, "-u", "root", "-e", "true"], capture_output=True)
    if prueba.returncode != 0:
        print(f"❌ La distribución '{distro}' no terminó su configuración inicial (no existe el usuario root).")
        print(f"   Solución: abre una terminal y ejecuta:  wsl -d {distro}")
        print("   Crea tu usuario y contraseña cuando lo pida, escribe 'exit' y vuelve a probar.")
        print(f"   Si sigue igual:  wsl --unregister {distro}   y luego   wsl --install -d {distro}")
        return False

    # Dependencias como root (no pide contraseña)
    r = subprocess.run(["wsl", "-d", distro, "-u", "root", "-e", "bash", ruta_a_wsl(deps)])
    if r.returncode != 0:
        print("❌ No se pudieron instalar las dependencias en WSL.")
        return False

    print("🚀 Lanzando la app (WSLg la mostrará como una ventana de Windows)...")
    print("   Requiere Windows 11 o Windows 10 reciente con WSLg.")
    subprocess.Popen(["wsl", "-d", distro, "-e", "bash", ruta_a_wsl(run), ruta_a_wsl(tar)])
    return True


def nuevo_archivo(carpeta, extension, desde):
    """True si hay un archivo con esa extensión modificado después de 'desde'."""
    if not os.path.isdir(carpeta):
        return False
    return any(
        f.endswith(extension) and os.path.getmtime(os.path.join(carpeta, f)) >= desde
        for f in os.listdir(carpeta)
    )

# ---------------------------------------------------------------------------
# Compilación
# ---------------------------------------------------------------------------
def build_web():
    print("\n--- 🌐 COMPILANDO PARA WEB ---")
    crear_carpetas_builds()
    preparar_proyecto()
    env = os.environ.copy()
    env["CI"] = "true"

    if not run_command("ionic build --prod", cwd=PROJECT_DIR, env=env):
        print("❌ Error al compilar para la web.")
        return False

    src = carpeta_web_resultante()
    if not src:
        print("❌ No se encontró index.html en www/ ni www/browser/.")
        return False

    shutil.rmtree(WEB_BUILD_DIR, ignore_errors=True)
    shutil.copytree(src, WEB_BUILD_DIR)
    print(f"✅ Web copiada en: {os.path.abspath(WEB_BUILD_DIR)}")
    return True


def build_android(instalar=False):
    print("\n--- 📱 COMPILANDO APK (Android) ---")
    crear_carpetas_builds()
    cfg, img = preparar_proyecto()

    if not os.path.isdir(ANDROID_SDK_PATH):
        print(f"❌ No existe el SDK de Android en: {ANDROID_SDK_PATH}")
        return False

    env = os.environ.copy()
    env["CI"] = "true"
    env["ANDROID_HOME"] = ANDROID_SDK_PATH
    env["ANDROID_SDK_ROOT"] = ANDROID_SDK_PATH

    java_path = encontrar_java_valido()
    if not java_path:
        print(f"❌ No hay Java {MIN_JAVA}-{MAX_JAVA}. Instala: winget install EclipseAdoptium.Temurin.21.JDK")
        return False
    env["JAVA_HOME"] = java_path
    env["PATH"] = os.path.join(java_path, "bin") + os.pathsep + env.get("PATH", "")

    # 'add android' necesita que exista el build web
    if not carpeta_web_resultante():
        if not run_command("ionic build", cwd=PROJECT_DIR, env=env):
            return False

    if not os.path.exists(ANDROID_DIR):
        print("Plataforma Android no encontrada. Agregándola...")
        if not run_command("ionic capacitor add android", cwd=PROJECT_DIR, env=env):
            return False

    if not run_command("ionic capacitor sync android", cwd=PROJECT_DIR, env=env):
        return False

    configurar_gradle(java_path)
    aplicar_config_android(cfg, img)

    # Detener daemons viejos que pudieron quedar con Java 26
    run_command(f"{GRADLEW_CMD} --stop", cwd=ANDROID_DIR, env=env)

    print("\nGenerando APK de depuración con Gradle...")
    if not run_command(f"{GRADLEW_CMD} assembleDebug", cwd=ANDROID_DIR, env=env):
        print("❌ Error al compilar el APK con Gradle.")
        return False

    apk_src = os.path.join(ANDROID_DIR, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
    if not os.path.exists(apk_src):
        print("❌ No se encontró el APK en la ruta esperada.")
        return False

    apk_dest = os.path.join(APK_BUILD_DIR, "app-debug.apk")
    shutil.copy(apk_src, apk_dest)
    con_version = os.path.join(APK_BUILD_DIR, f"{slug(cfg['appName'])}-{cfg['version']}.apk")
    shutil.copy(apk_src, con_version)
    print(f"✅ APK copiado a: {os.path.abspath(con_version)}")
    if instalar:
        instalar_apk(apk_dest)
    return True


def build_desktop(quiere=("exe", "linux"), rebuild_web=True):
    print("\n--- 💻 GENERANDO ESCRITORIO ---")
    crear_carpetas_builds()
    cfg, img = preparar_proyecto()

    env = os.environ.copy()
    env["CI"] = "true"
    env["CSC_IDENTITY_AUTO_DISCOVERY"] = "false"  # sin firma de código

    objetivos = []
    if "exe" in quiere:
        if IS_WIN:
            objetivos.append(("Windows (.exe portable)", "npx electron-builder --win portable --x64",
                              ".exe", EXE_BUILD_DIR))
        else:
            print("⚠️ El .exe solo se puede generar desde Windows.")
    if "linux" in quiere:
        if IS_WIN:
            objetivos.append(("Linux (.tar.gz con ejecutable)", "npx electron-builder --linux tar.gz --x64",
                              ".tar.gz", LINUX_BUILD_DIR))
        elif platform.system() == "Linux":
            objetivos.append(("Linux (.AppImage)", "npx electron-builder --linux AppImage --x64",
                              ".AppImage", LINUX_BUILD_DIR))
        else:
            print("⚠️ Sistema no soportado para empaquetar Linux.")
    if not objetivos:
        return False

    # 1. Build web (prod)
    if rebuild_web or not carpeta_web_resultante():
        if not run_command("ionic build --prod", cwd=PROJECT_DIR, env=env):
            print("❌ Falló el build web.")
            return False
    src = carpeta_web_resultante()
    if not src:
        print("❌ No se encontró index.html en www/.")
        return False

    # 2. Proyecto Electron con la configuración actual
    escribir_proyecto_electron(cfg, img)

    # 3. Copiar la web dentro del proyecto Electron
    app_dir = os.path.join(DESKTOP_DIR, "app")
    shutil.rmtree(app_dir, ignore_errors=True)
    shutil.copytree(src, app_dir)

    # 4. Instalar dependencias (solo si faltan)
    if not os.path.isdir(os.path.join(DESKTOP_DIR, "node_modules")):
        if not run_command("npm install", cwd=DESKTOP_DIR, env=env):
            return False

    # 5. Empaquetar cada objetivo
    dist = os.path.join(DESKTOP_DIR, "dist")
    todo_ok = True
    for nombre, cmd, patron, destino in objetivos:
        print(f"\n>>> Empaquetando {nombre}")
        shutil.rmtree(dist, ignore_errors=True)
        if not run_command(cmd, cwd=DESKTOP_DIR, env=env):
            print(f"❌ Falló el empaquetado de {nombre}.")
            if "Windows" in nombre:
                print("   Si ves 'Cannot create symbolic link', activa el Modo desarrollador de Windows")
                print("   (Configuración > Sistema > Para programadores) o ejecuta como administrador.")
            else:
                print("   Alternativa: ejecuta este script dentro de WSL/Linux para generar el Linux nativo.")
            todo_ok = False
            continue

        generados = [f for f in os.listdir(dist) if f.endswith(patron)] if os.path.isdir(dist) else []
        if not generados:
            print(f"❌ No se encontró el archivo {patron} en desktop/dist.")
            todo_ok = False
            continue
        for archivo in generados:
            shutil.copy(os.path.join(dist, archivo), os.path.join(destino, archivo))
            print(f"✅ Listo: {os.path.abspath(os.path.join(destino, archivo))}")

    return todo_ok


def resumen_compilacion(inicio, ok_web):
    """Imprime qué se generó en esta corrida y devuelve (hay_apk, hay_exe, hay_linux)."""
    hay_apk = nuevo_archivo(APK_BUILD_DIR, ".apk", inicio)
    hay_exe = nuevo_archivo(EXE_BUILD_DIR, ".exe", inicio) if IS_WIN else False
    if IS_WIN:
        hay_linux = nuevo_archivo(LINUX_BUILD_DIR, ".tar.gz", inicio)
    else:
        hay_linux = nuevo_archivo(LINUX_BUILD_DIR, ".AppImage", inicio)

    print("\n=== 📋 RESUMEN DE COMPILACIÓN ===")
    print(f"  {'✅' if ok_web else '❌'} Web")
    print(f"  {'✅' if hay_apk else '❌'} APK")
    if IS_WIN:
        print(f"  {'✅' if hay_exe else '❌'} Ejecutable Windows (.exe)")
    print(f"  {'✅' if hay_linux else '❌'} Linux ({'.tar.gz' if IS_WIN else '.AppImage'})")
    if not hay_apk:
        print("  ↳ El APK falló: revisa el error de Gradle más arriba en la consola.")
    return hay_apk, hay_exe, hay_linux


def compilar_todos():
    inicio = time.time()
    ok_web = build_web()
    # El escritorio va antes que el APK: 'capacitor sync' reconstruye www en modo desarrollo
    build_desktop(("exe", "linux"), rebuild_web=False)
    build_android()
    resumen_compilacion(inicio, ok_web)

# ---------------------------------------------------------------------------
# Correr / probar (APK)
# ---------------------------------------------------------------------------
def _leer_gradle():
    gradle = os.path.join(ANDROID_DIR, "app", "build.gradle")
    if os.path.exists(gradle):
        with open(gradle, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def obtener_package_id():
    """applicationId real del proyecto Android (build.gradle) o appId de Capacitor."""
    m = re.search(r"""applicationId\s*=?\s*["']([\w.]+)["']""", _leer_gradle())
    if m:
        return m.group(1)
    cfg = os.path.join(ANDROID_DIR, "app", "src", "main", "assets", "capacitor.config.json")
    if os.path.exists(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                return json.load(f).get("appId")
        except Exception:
            pass
    return None


def obtener_namespace():
    """Paquete interno del código (donde vive MainActivity)."""
    m = re.search(r"""namespace\s*=?\s*["']([\w.]+)["']""", _leer_gradle())
    return m.group(1) if m else None


def correr_apk():
    print("\n--- 📱 CORRIENDO APK EN EL CELULAR ---")
    apk = os.path.join(APK_BUILD_DIR, "app-debug.apk")
    if not os.path.exists(apk):
        print("⚠️ No hay APK en builds/apk. Primero compílalo desde el menú Compilar.")
        return False

    adb = obtener_adb()
    if not adb:
        print("⚠️ No se encontró adb.")
        return False

    dispositivo = dispositivo_listo(adb)
    if not dispositivo:
        return False

    package = obtener_package_id()
    if package:
        print(f"🗑️ Desinstalando la versión anterior ({package}) del celular...")
        _, salida = adb_run(adb, ["-s", dispositivo, "uninstall", package])
        if "Success" in salida:
            print("   ✅ Versión anterior eliminada.")
        else:
            print("   ℹ️ No había versión anterior instalada (o no se pudo borrar). Se continúa.")
    else:
        print("⚠️ No pude detectar el package, se instalará encima de la versión existente.")

    print(f"📲 Instalando el APK nuevo en {dispositivo}...")
    codigo, salida = adb_run(adb, ["-s", dispositivo, "install", "-r", apk])
    print(salida)
    if "Success" not in salida:
        print("❌ La instalación falló. Posibles causas:")
        if "USER_RESTRICTED" in salida:
            print("   - Activa 'Instalar vía USB' / 'Instalación USB' en Opciones de desarrollador (Xiaomi, Oppo, Vivo).")
        if "UPDATE_INCOMPATIBLE" in salida or "VERSION_DOWNGRADE" in salida:
            print("   - Desinstala primero la app del celular (tiene otra firma o una versión más nueva).")
        if "INSUFFICIENT_STORAGE" in salida:
            print("   - Libera espacio en el celular.")
        print("   - Mira si el celular muestra un cuadro pidiendo permiso para instalar.")
        return False

    if not package:
        print("⚠️ APK instalado, pero no pude detectar el package. Ábrelo manualmente en el celular.")
        return False

    print(f"🚀 Abriendo {package}...")
    adb_run(adb, ["-s", dispositivo, "shell", "input", "keyevent", "KEYCODE_WAKEUP"])
    _, salida = adb_run(adb, ["-s", dispositivo, "shell", "monkey", "-p", package,
                              "-c", "android.intent.category.LAUNCHER", "1"])
    if "No activities found" in salida or "monkey aborted" in salida:
        print("   monkey no pudo abrirla, probando con am start...")
        ns = obtener_namespace() or package
        _, salida = adb_run(adb, ["-s", dispositivo, "shell", "am", "start", "-n",
                                  f"{package}/{ns}.MainActivity"])
        print(salida)
        if "Error" in salida:
            print("❌ No se pudo abrir automáticamente. Ábrela manualmente: ya quedó instalada.")
            return False

    print("✅ App lanzada. Si no la ves, desbloquea la pantalla del celular.")
    return True


def probar_todo():
    """Prueba todo lo que ya esté compilado (la web va al final: se queda corriendo)."""
    print("\n=== ▶️ PROBANDO TODO LO COMPILADO ===")
    correr_exe()
    if IS_WIN:
        correr_linux_wsl()
    correr_apk()
    correr_web()


def compilar_todo_y_probar():
    print("\n=== 🚀 COMPILAR TODO Y PROBAR ===")
    inicio = time.time()
    ok_web = build_web()
    build_desktop(("exe", "linux"), rebuild_web=False)
    build_android()
    hay_apk, hay_exe, hay_linux = resumen_compilacion(inicio, ok_web)

    if not (ok_web or hay_apk or hay_exe or hay_linux):
        print("\n❌ No se compiló nada, no hay qué probar.")
        return

    print("\n=== ▶️ PROBANDO LOS COMPILADOS ===")
    if hay_exe:
        correr_exe()
    if hay_linux:
        if IS_WIN:
            correr_linux_wsl()
        else:
            correr_exe()
    if hay_apk:
        correr_apk()
    if ok_web:
        correr_web()


# ---------------------------------------------------------------------------
# Configuración interactiva
# ---------------------------------------------------------------------------
def mostrar_config():
    cfg = cargar_config()
    print("\n--- ⚙️ CONFIGURACIÓN ACTUAL ---")
    print(f"  Nombre de la app : {cfg['appName']}")
    print(f"  Paquete (appId)  : {cfg['appId']}")
    print(f"  Versión          : {cfg['version']}  (versionCode Android: {version_code(cfg['version'])})")
    icono = cfg["icon"] if cfg["icon"] and os.path.exists(cfg["icon"]) else "(sin icono)"
    print(f"  Icono            : {icono}")
    print(f"  Icono dentro del .exe: {'sí' if cfg['exe_embed_icon'] else 'no'}")


def cfg_nombre():
    cfg = cargar_config()
    print(f"\nNombre actual: {cfg['appName']}")
    nuevo = input("Nuevo nombre de la app (vacío = cancelar): ").strip()
    if not nuevo:
        return
    if len(nuevo) > 40:
        print("❌ Máximo 40 caracteres.")
        return
    cfg["appName"] = nuevo
    guardar_config(cfg)
    print("✅ Guardado. Se aplicará en la próxima compilación.")


def cfg_paquete():
    cfg = cargar_config()
    print(f"\nPaquete actual: {cfg['appId']}")
    print("Formato: letras, números y '_' separados por puntos, ej: com.miempresa.miapp")
    nuevo = input("Nuevo paquete (vacío = cancelar): ").strip()
    if not nuevo:
        return
    if not valida_app_id(nuevo):
        print("❌ Paquete inválido. Ejemplo válido: com.miempresa.miapp")
        return
    cfg["appId"] = nuevo
    guardar_config(cfg)
    print("✅ Guardado. Se aplicará en la próxima compilación.")
    print("ℹ️ Android trata un paquete distinto como OTRA app: la anterior seguirá instalada en el celular.")


def cfg_version():
    cfg = cargar_config()
    print(f"\nVersión actual: {cfg['version']}")
    nuevo = input("Nueva versión, formato X.Y.Z (vacío = cancelar): ").strip()
    if not nuevo:
        return
    if not valida_version(nuevo):
        print("❌ Versión inválida. Ejemplo: 1.2.0")
        return
    cfg["version"] = nuevo
    guardar_config(cfg)
    print(f"✅ Guardado (versionCode Android: {version_code(nuevo)}).")


def cfg_icono():
    cfg = cargar_config()
    print("\nImagen PNG/JPG, ideal cuadrada de 1024x1024.")
    ruta = input("Ruta de la imagen (vacío = quitar el icono): ").strip().strip('"').strip("'")

    if not ruta:
        if cfg["icon"] and os.path.exists(cfg["icon"]):
            os.remove(cfg["icon"])
        cfg["icon"] = ""
        guardar_config(cfg)
        print("✅ Icono quitado (se usará el de la plantilla).")
        return

    if not os.path.isfile(ruta):
        print("❌ No existe ese archivo.")
        return
    if not asegurar_pillow():
        print("❌ No se pudo instalar Pillow (pip install pillow).")
        return

    from PIL import Image
    try:
        img = Image.open(ruta).convert("RGBA")
    except Exception as e:
        print(f"❌ No se pudo abrir la imagen: {e}")
        return

    w, h = img.size
    if w != h:
        lado = min(w, h)
        izq, arr = (w - lado) // 2, (h - lado) // 2
        img = img.crop((izq, arr, izq + lado, arr + lado))
        print(f"ℹ️ La imagen no era cuadrada ({w}x{h}); se recortó al centro.")
    if img.size[0] < 512:
        print(f"⚠️ La imagen es pequeña ({img.size[0]}px); se verá borrosa. Recomendado 1024x1024.")

    os.makedirs(ASSETS_DIR, exist_ok=True)
    img.save(ICON_STORE)
    cfg["icon"] = ICON_STORE
    guardar_config(cfg)
    print("✅ Icono guardado. Se aplicará en Android, escritorio y web en la próxima compilación.")


def cfg_icono_exe():
    cfg = cargar_config()
    cfg["exe_embed_icon"] = not cfg["exe_embed_icon"]
    guardar_config(cfg)
    if cfg["exe_embed_icon"]:
        print("✅ Activado: el icono se incrusta en el .exe.")
        print("   Requiere el Modo desarrollador de Windows (o terminal como administrador);")
        print("   si falla con 'Cannot create symbolic link', desactívalo aquí.")
    else:
        print("✅ Desactivado: el .exe usa el icono de Electron en el Explorador,")
        print("   pero la ventana de la app sí muestra tu icono.")


def cfg_restablecer():
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    shutil.rmtree(ASSETS_DIR, ignore_errors=True)
    print("✅ Configuración restablecida (se leerán de nuevo los valores del proyecto).")


# ---------------------------------------------------------------------------
# Menús
# ---------------------------------------------------------------------------
def menu_generico(titulo, opciones, volver="Volver", cabecera=None):
    """opciones: lista de (texto, función) o función que devuelve esa lista."""
    while True:
        ops = opciones() if callable(opciones) else opciones
        print(f"\n--------- {titulo} ---------")
        if cabecera:
            cabecera()
        for i, (texto, _) in enumerate(ops, 1):
            print(f"{i}. {texto}")
        print(f"{len(ops) + 1}. {volver}")

        choice = input(f"\nSelecciona una opción (1-{len(ops) + 1}): ").strip()
        if choice == str(len(ops) + 1):
            return
        if choice.isdigit() and 1 <= int(choice) <= len(ops):
            ops[int(choice) - 1][1]()
        else:
            print("Opción inválida.")


def linea_config():
    cfg = cargar_config()
    print(f"📦 {cfg['appName']} · {cfg['appId']} · v{cfg['version']}")


def menu_compilar():
    menu_generico("🔨 COMPILAR", [
        ("Web", build_web),
        ("Ejecutable Windows (.exe)", lambda: build_desktop(("exe",))),
        ("Linux (.tar.gz / .AppImage)", lambda: build_desktop(("linux",))),
        ("APK (Android)", build_android),
        ("TODOS", compilar_todos),
    ], cabecera=linea_config)


def menu_probar():
    menu_generico("▶️ PROBAR", [
        ("Web (servidor local + navegador)", correr_web),
        ("Ejecutable Windows (.exe)", correr_exe),
        ("APK en el celular (desinstala, instala y abre)", correr_apk),
        ("Linux en WSL", correr_linux_wsl),
        ("TODO lo compilado", probar_todo),
    ], cabecera=linea_config)


def menu_configurar():
    def opciones():
        cfg = cargar_config()
        return [
            (f"Nombre de la app  [{cfg['appName']}]", cfg_nombre),
            (f"Nombre del paquete [{cfg['appId']}]", cfg_paquete),
            (f"Versión [{cfg['version']}]", cfg_version),
            (f"Icono [{'configurado' if cfg['icon'] and os.path.exists(cfg['icon']) else 'sin icono'}]", cfg_icono),
            (f"Incrustar icono en el .exe [{'sí' if cfg['exe_embed_icon'] else 'no'}]", cfg_icono_exe),
            ("Ver configuración completa", mostrar_config),
            ("Restablecer configuración", cfg_restablecer),
        ]
    menu_generico("⚙️ CONFIGURAR", opciones)


def menu():
    while True:
        print("\n========================================")
        print("   🛠️ BUILDER AUTOMÁTICO (IONIC + BUILDS)")
        print("========================================")
        linea_config()
        print("1. 🔨 Compilar   (web, exe, linux, apk, todos)")
        print("2. ▶️ Probar     (web, exe, apk, linux, todo)")
        print("3. ⚙️ Configurar (nombre, paquete, versión, icono)")
        print("4. 🚀 Compilar TODO y probar")
        print("5. Salir")

        choice = input("\nSelecciona una opción (1-5): ").strip()

        if choice == "1":
            menu_compilar()
        elif choice == "2":
            menu_probar()
        elif choice == "3":
            menu_configurar()
        elif choice == "4":
            compilar_todo_y_probar()
        elif choice == "5":
            print("¡Hasta luego!")
            sys.exit(0)
        else:
            print("Opción inválida. Inténtalo de nuevo.")


if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")