import yaml
import os
from nornir import InitNornir
from nornir_napalm.plugins.tasks import napalm_get
from nornir.core.filter import F
from datetime import datetime
import time
import threading
import telebot

# TOKEN del bot (debes mantenerlo seguro y no compartirlo)
TOKEN = "8091293463:AAFZCmV4AbQPZ4uO3JPChPaRL9q3EkypEMA"
bot = telebot.TeleBot(TOKEN)

# Variables globales para el monitoreo
previous_state = {}
monitoreo_activo = True

# Función para obtener errores en las interfaces de red
def get_interface_errors(task):
    result = task.run(task=napalm_get, getters=["interfaces"])
    interfaces = result.result["interfaces"]
    report = []
    state_changes = []
    
    global previous_state
    current_state = {}

    for interface, stats in interfaces.items():
        # Guardar estado actual
        current_state[interface] = {
            "is_up": stats.get("is_up"),
            "is_enabled": stats.get("is_enabled"),
            "tx_errors": stats.get("tx_errors", 0),
            "rx_errors": stats.get("rx_errors", 0),
            "input_drops": stats.get("input_drops"),
            "output_drops": stats.get("output_drops", 0),
        }
        
        # Comprobar cambios de estado
        if interface in previous_state:
            prev = previous_state[interface]
            if (prev["is_up"] != current_state[interface]["is_up"] or 
                prev["is_enabled"] != current_state[interface]["is_enabled"] or 
                prev["tx_errors"] != current_state[interface]["tx_errors"] or 
                prev["rx_errors"] != current_state[interface]["rx_errors"] or
                prev["input_drops"] != current_state[interface]["input_drops"] or 
                prev["output_drops"] != current_state[interface]["output_drops"]):
                state_changes.append(f"Cambio detectado en {interface}:\n {current_state[interface]}")
        
        if stats.get("is_up") is False or stats.get("is_enabled") is False:
            error_message = f"La interfaz {interface} está caída o deshabilitada.\n"
            report.append(error_message)
        elif stats.get("tx_errors", 0) > 0 or stats.get("rx_errors", 0) > 0:
            error_message = f"La interfaz {interface} tiene errores TX: {stats.get('tx_errors')}, RX: {stats.get('rx_errors')}.\n"
            report.append(error_message)
        elif stats.get("input_drops", 0) > 0 or stats.get("output_drops", 0) > 0:
            error_message = f"La interfaz {interface} tiene drops: Input Drops: {stats.get('input_drops')}, Output Drops: {stats.get('output_drops')}.\n"
            report.append(error_message)
        else:
            state = f"La interfaz {interface} está operativa.\n"
            report.append(state)

    # Actualizar estado anterior
    previous_state = current_state

    return report, state_changes

# Funciones auxiliares
def crear_direc():
    directory = "Reportes"
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory

def guardar_reporte(report, filename):
    directory = crear_direc()
    filepath = os.path.join(directory, filename)
    with open(filepath, "w") as f:
        f.write("\n".join(report))
    return filepath

# Funciones para generar reportes
def generar_reporte_individual(nr, device_name):
    device = nr.filter(F(name=device_name))
    if not device.inventory.hosts:
        return None, f"No se encontró el dispositivo {device_name} en el inventario."
    
    result = device.run(task=get_interface_errors)
    report = []
    for task_result in result.values():
        report.append(f"== Reporte de {device_name} ==")
        for r in task_result:
            report.extend(r.result)
    
    if report:
        filename = f"reporte_{device_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = guardar_reporte(report, filename)
        return filepath, "\n".join(report)
    else:
        return None, f"No se encontraron errores en el dispositivo {device_name}."

def generar_reporte_total(nr):
    result = nr.run(task=get_interface_errors)
    report = []
    for device_name, task_result in result.items():
        report.append(f"== Reporte de {device_name} ==")
        for r in task_result:
            report.extend(r.result)
    
    if report:
        filename = f"reporte_combinado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = guardar_reporte(report, filename)
        return filepath, "\n".join(report)
    else:
        return None, "No se encontraron errores en los dispositivos."

# Monitoreo automático
def monitoreo_automatico(nr, chat_id):
    while monitoreo_activo:
        result = nr.run(task=get_interface_errors)
        report = []
        state_changes = []

        for device_name, task_result in result.items():
            report.append(f"\n{'='*20} Reporte de {device_name} {'='*20}\n")
            for r in task_result:
                errores, cambios = r.result
                report.extend(errores)
                state_changes.extend(cambios)

        if state_changes:
            filename = f"reporte_automatico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = guardar_reporte(report, filename)

            # Enviar reporte automáticamente
            with open(filepath, 'rb') as file:
                bot.send_document(chat_id, file)

            bot.send_message(chat_id, "Se detectaron cambios en el estado de las interfaces. Revisa el reporte adjunto.")
        time.sleep(60) 


# Inicialización de Nornir
nr = InitNornir(config_file="config.yaml")




# Comandos del bot
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "¡Hola! Soy tu bot de monitoreo de redes. Usa /reporte para generar reportes.")

@bot.message_handler(commands=["reporte"])
def menu_reporte(message):
    opciones = (
        "Opciones:\n"
        "1. /reporte_individual <nombre_dispositivo> - Generar reporte para un dispositivo específico.\n"
        "2. /reporte_total - Generar reporte combinado de todos los dispositivos.\n"
        "3. /listar_dispositivos - Ver la lista de dispositivos disponibles.\n"
        "4. /iniciar_monitoreo - Empieza monitoreo automatico\n"
        "5. /detener_monitoreo - Detiene monitoreo automatico"
    )
    bot.reply_to(message, opciones)

@bot.message_handler(commands=["reporte_individual"])
def reporte_individual(message):
    try:
        device_name = message.text.split()[1]
        filepath, result_message = generar_reporte_individual(nr, device_name)
        
        if filepath:
            # Enviar archivo
            with open(filepath, 'rb') as file:
                bot.send_document(message.chat.id, file)
            
            # Enviar mensaje adicional
            bot.send_message(message.chat.id, result_message)
        else:
            bot.reply_to(message, result_message)
    
    except IndexError:
        bot.reply_to(message, "Por favor, proporciona el nombre del dispositivo. Ejemplo: /reporte_individual dispositivo1")

@bot.message_handler(commands=["reporte_total"])
def reporte_total(message):
    filepath, result_message = generar_reporte_total(nr)
    
    if filepath:
        # Enviar archivo
        with open(filepath, 'rb') as file:
            bot.send_document(message.chat.id, file)
        
        # Enviar mensaje adicional
        bot.send_message(message.chat.id, result_message)
    else:
        bot.reply_to(message, result_message)

@bot.message_handler(commands=["listar_dispositivos"])
def listar_dispositivos(message):
    # Obtiene la lista de dispositivos desde el inventario de Nornir
    dispositivos = nr.inventory.hosts.keys()
    if dispositivos:
        dispositivos_str = "\n".join(dispositivos)
        bot.reply_to(message, f"Dispositivos disponibles:\n{dispositivos_str}")
    else:
        bot.reply_to(message, "No hay dispositivos disponibles en el inventario.")

@bot.message_handler(commands=["iniciar_monitoreo"])
def iniciar_monitoreo(message):
    chat_id = message.chat.id
    bot.reply_to(message, "Monitoreo automático activado. Se enviarán reportes si se detectan cambios en los dispositivos.")
    threading.Thread(target=monitoreo_automatico, args=(nr, chat_id)).start()

@bot.message_handler(commands=["detener_monitoreo"])
def detener_monitoreo(message):
    global monitoreo_activo
    monitoreo_activo = False
    bot.reply_to(message, "Monitoreo automático detenido.")

# Iniciar el bot
bot.polling()