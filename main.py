import flet as ft
import flet_geolocator as ftg
import flet_map as ftm
import math
import time
import urllib.request
import urllib.parse
import json
import asyncio

# --- CÁLCULO DE VELOCIDAD (HAVERSINE) ---
def calcular_velocidad(pos_anterior, pos_actual):
    R = 6371000
    lat1, lon1, t1 = math.radians(pos_anterior['lat']), math.radians(pos_anterior['lon']), pos_anterior['timestamp']
    lat2, lon2, t2 = math.radians(pos_actual['lat']), math.radians(pos_actual['lon']), pos_actual['timestamp']
    a = math.sin((lat2 - lat1) / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return ((R * c) / (t2 - t1)) * 3.6 if (t2 - t1) > 0 else 0.0

# --- PETICIONES WEB ASÍNCRONAS ---
async def obtener_json(url):
    def _fetch():
        req = urllib.request.Request(url, headers={'User-Agent': 'HUDApp/1.0'})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        print(f"Error de red: {e}")
        return None

# ==========================================
# CLASE 1: VELOCÍMETRO (DOBLE TOQUE IZQUIERDO)
# ==========================================
class VelocimetroHUD(ft.Container):
    def __init__(self, on_double_tap):
        super().__init__()
        self.expand = 1 
        self.alignment = ft.Alignment(0, 0)
        
        self.speed_text = ft.Text("0", size=130, color=ft.Colors.GREEN_ACCENT_400, weight=ft.FontWeight.BOLD)
        self.unit_text = ft.Text("km/h", size=30, color=ft.Colors.WHITE70)
        
        # Eliminado el Switch. Ahora es un contenedor puro.
        self.hud_content = ft.Container(
            content=ft.Column(
                [self.speed_text, self.unit_text],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=0 
            ),
            scale=ft.Scale(scale_x=1, scale_y=1)
        )
        
        # El detector de gestos envuelve toda la mitad izquierda
        self.content = ft.GestureDetector(
            on_double_tap=on_double_tap,
            content=self.hud_content
        )

    def toggle_espejo(self, activar: bool):
        self.hud_content.scale = ft.Scale(scale_x=-1 if activar else 1, scale_y=1)
        self.update()

    def actualizar_velocidad(self, velocidad: int):
        self.speed_text.value = str(velocidad)
        self.update()

# ==========================================
# CLASE 2: MAPA (DOBLE TOQUE DERECHO)
# ==========================================
class MapaNavegacion(ft.Container):
    def __init__(self, on_double_tap):
        super().__init__()
        self.expand = 1 
        self.alignment = ft.Alignment(0, 0)
        
        self.coordenada_actual = ftm.MapLatitudeLongitude(40.4167, -3.7037)
        self.marcador = ftm.Marker(content=ft.Icon(ft.Icons.NAVIGATION, color=ft.Colors.BLUE_ACCENT_400, size=35), coordinates=self.coordenada_actual)
        
        self.capa_base = ftm.TileLayer(url_template="https://a.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png")
        self.capa_ruta = ftm.PolylineLayer(polylines=[]) 
        self.capa_marcadores = ftm.MarkerLayer(markers=[self.marcador])
        
        self.mapa = ftm.Map(
            expand=True,
            initial_center=self.coordenada_actual,
            initial_zoom=18,
            layers=[self.capa_base, self.capa_ruta, self.capa_marcadores],
        )

        self.icono_giro = ft.Icon(ft.Icons.STRAIGHT, size=100, color=ft.Colors.AMBER_400)
        self.distancia_giro = ft.Text("---", size=40, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
        self.calle_texto = ft.Text("Modo Libre", size=20, color=ft.Colors.WHITE70, text_align=ft.TextAlign.CENTER)
        
        self.contenedor_flechas = ft.Container(
            expand=1,
            content=ft.Column([self.icono_giro, self.distancia_giro, self.calle_texto], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            visible=False # Oculto en modo libre
        )

        # Envolvemos el contenido interior para poder invertirlo todo (texto, flechas y geografía)
        self.inner_content = ft.Container(
            content=ft.Row([ft.Container(expand=1, content=self.mapa), self.contenedor_flechas], expand=True),
            scale=ft.Scale(scale_x=1, scale_y=1)
        )

        # El detector de gestos envuelve toda la mitad derecha
        self.content = ft.GestureDetector(
            on_double_tap=on_double_tap,
            content=self.inner_content
        )

    def toggle_espejo(self, activar: bool):
        self.inner_content.scale = ft.Scale(scale_x=-1 if activar else 1, scale_y=1)
        self.update()

    def detener_navegacion(self):
        self.contenedor_flechas.visible = False
        self.capa_ruta.polylines = []
        self.update()

    async def actualizar_posicion(self, lat, lon):
        self.coordenada_actual = ftm.MapLatitudeLongitude(lat, lon)
        self.marcador.coordinates = self.coordenada_actual
        self.update()
        try:
            await self.mapa.move_to(self.coordenada_actual, zoom=18)
        except Exception:
            pass

    async def activar_navegacion(self, lat_origen, lon_origen, destino_texto):
        self.contenedor_flechas.visible = True
        self.calle_texto.value = "Buscando calle..."
        self.update()

        url_nom = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(destino_texto)}&format=json&limit=1"
        res_nom = await obtener_json(url_nom)
        
        if not res_nom:
            self.calle_texto.value = "Destino no encontrado"
            self.update()
            return
            
        lat_dest, lon_dest = res_nom[0]['lat'], res_nom[0]['lon']

        url_osrm = f"https://router.project-osrm.org/route/v1/driving/{lon_origen},{lat_origen};{lon_dest},{lat_dest}?steps=true&geometries=geojson"
        res_osrm = await obtener_json(url_osrm)
        
        if not res_osrm or 'routes' not in res_osrm:
            self.calle_texto.value = "Error calculando ruta"
            self.update()
            return

        ruta = res_osrm['routes'][0]
        geometria = ruta['geometry']['coordinates']
        pasos = ruta['legs'][0]['steps']

        puntos_linea = [ftm.MapLatitudeLongitude(coord[1], coord[0]) for coord in geometria]
        self.capa_ruta.polylines = [ftm.PolylineMarker(coordinates=puntos_linea, color=ft.Colors.RED_ACCENT_400, stroke_width=6)]
        self.mapa.update()

        if len(pasos) > 1:
            primer_giro = pasos[1] 
            maniobra = primer_giro.get('maneuver', {})
            tipo_giro = maniobra.get('modifier', 'straight')
            
            iconos = {
                'left': ft.Icons.TURN_LEFT,
                'right': ft.Icons.TURN_RIGHT,
                'slight left': ft.Icons.TURN_SLIGHT_LEFT,
                'slight right': ft.Icons.TURN_SLIGHT_RIGHT,
                'sharp left': ft.Icons.TURN_SHARP_LEFT,
                'sharp right': ft.Icons.TURN_SHARP_RIGHT,
                'uturn': ft.Icons.U_TURN_LEFT,
                'straight': ft.Icons.STRAIGHT
            }
            
            self.icono_giro.name = iconos.get(tipo_giro, ft.Icons.STRAIGHT)
            self.distancia_giro.value = f"{int(primer_giro.get('distance', 0))} m"
            self.calle_texto.value = primer_giro.get('name', 'Continuar recto')
        
        self.update()

# ==========================================
# MAIN: CONTROLADOR GLOBAL
# ==========================================
async def main(page: ft.Page):
    page.bgcolor = ft.Colors.BLACK
    page.padding = 0 # Eliminamos márgenes para que sea inmersivo
    
    page.wake_lock = True
    try: page.window.prevent_sleep = True
    except Exception: pass 
    
    estado_espejo = False

    # 1. GESTIÓN DEL ESPEJO GLOBAL
    def alternar_espejo(e):
        nonlocal estado_espejo
        estado_espejo = not estado_espejo
        panel_izquierdo.toggle_espejo(estado_espejo)
        mapa_nav.toggle_espejo(estado_espejo)

    # 2. GESTIÓN DE OPCIONES DE MAPA (DOBLE TOQUE DERECHO)
    def abrir_opciones(e):
        input_destino.value = ""
        dlg_opciones.open = True
        page.update()

    # Instanciamos los módulos permanentemente
    panel_izquierdo = VelocimetroHUD(on_double_tap=alternar_espejo)
    mapa_nav = MapaNavegacion(on_double_tap=abrir_opciones)

    ultima_posicion = None

    # Tarea que se lanza al pedir una ruta
    async def cargar_ruta(destino_texto):
        lat = ultima_posicion['lat'] if ultima_posicion else 40.4167
        lon = ultima_posicion['lon'] if ultima_posicion else -3.7037
        await mapa_nav.activar_navegacion(lat, lon, destino_texto)

    # --- LÓGICA DEL GPS ---
    async def on_position_change(e: ftg.GeolocatorPositionChangeEvent):
        nonlocal ultima_posicion
        speed_native = e.position.speed if e.position.speed is not None else 0.0
        t_actual = time.time()
        pos_actual = {'lat': e.position.latitude, 'lon': e.position.longitude, 'timestamp': t_actual}
        
        speed_calc = calcular_velocidad(ultima_posicion, pos_actual) if ultima_posicion else 0.0
        ultima_posicion = pos_actual
        
        velocidad_final = (speed_native * 3.6) if speed_native > 0 else speed_calc
        if velocidad_final < 1.5: velocidad_final = 0

        panel_izquierdo.actualizar_velocidad(int(velocidad_final))
        await mapa_nav.actualizar_posicion(e.position.latitude, e.position.longitude)

    geo = ftg.Geolocator(
        on_position_change=on_position_change,
        configuration=ftg.GeolocatorConfiguration(accuracy=ftg.GeolocatorPositionAccuracy.HIGH),
    )
    
    try: page.services.append(geo)
    except AttributeError: page.overlay.append(geo)

    # El GPS arranca invisiblemente al abrir la app
    async def tarea_conectar_gps():
        await asyncio.sleep(0.5) 
        try:
            if not page.web: await geo.request_permission()
            await geo.get_current_position()
        except Exception as perm_ex:
            pass

    page.run_task(tarea_conectar_gps)

    # --- VENTANA EMERGENTE (DIÁLOGO DE OPCIONES) ---
    input_destino = ft.TextField(label="Destino (Ej: Plaza Mayor, Madrid)", autofocus=True)
    
    def accion_navegar(e):
        if input_destino.value:
            dlg_opciones.open = False
            page.update()
            page.run_task(cargar_ruta, input_destino.value)

    def accion_detener(e):
        dlg_opciones.open = False
        mapa_nav.detener_navegacion()
        page.update()

    def accion_cancelar(e):
        dlg_opciones.open = False
        page.update()

    dlg_opciones = ft.AlertDialog(
        title=ft.Text("Opciones de Navegación"), 
        content=ft.Column([
            input_destino,
            ft.Text("Selecciona una opción:", size=14, color=ft.Colors.WHITE54)
        ], tight=True),
        actions=[
            ft.Button("Detener Ruta", on_click=accion_detener, color=ft.Colors.RED_400),
            ft.Button("Cancelar", on_click=accion_cancelar),
            ft.Button("Navegar", on_click=accion_navegar, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)
        ]
    )
    
    page.overlay.append(dlg_opciones)

    # --- ENSAMBLAJE FINAL DE LA PANTALLA ---
    page.add(
        ft.Row([panel_izquierdo, ft.Container(expand=1, content=mapa_nav)], expand=True)
    )

ft.run(main, view=ft.AppView.WEB_BROWSER)
