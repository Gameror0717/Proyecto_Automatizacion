import yaml
import os
from nornir import InitNornir
from nornir_napalm.plugins.tasks import napalm_get
from nornir.core.filter import F
from datetime import datetime
import time
import telebot

# TOKEN del bot (debes mantenerlo seguro y no compartirlo)
TOKEN = "8091293463:AAFZCmV4AbQPZ4uO3JPChPaRL9q3EkypEMA"
bot = telebot.TeleBot(TOKEN)

# Función para obtener errores en las interfaces de red
def get_interface_errors(task):
    result = task.run(task=napalm_get, getters=["interfaces"])
    interfaces = result.result["interfaces"]
    report = []
    for interface, stats in interfaces.items():
        tx_utilization = stats.get("tx_bps", 0) / stats.get("speed", 1)
        rx_utilization = stats.get("rx_bps", 0) / stats.get("speed", 1)
        
        if stats.get("is_up") is False or stats.get("is_enabled") is False:
            error_message = f"La interfaz {interface} está caída o deshabilitada.\n"
            report.append(error_message)
        elif stats.get("tx_errors", 0) > 0 or stats.get("rx_errors", 0) > 0:
            error_message = f"La interfaz {interface} tiene errores TX: {stats.get('tx_errors')}, RX: {stats.get('rx_errors')}.\n"
            report.append(error_message)
        elif stats.get("input_drops", 0) > 0 or stats.get("output_drops", 0) > 0:
            error_message = f"La interfaz {interface} tiene drops: Input Drops: {stats.get('input_drops')}, Output Drops: {stats.get('output_drops')}.\n"
            report.append(error_message)
        elif tx_utilization > 0.8 or rx_utilization > 0.8:
            error_message = f"La interfaz {interface} está saturada (TX: {tx_utilization*100:.2f}%, RX: {rx_utilization*100:.2f}%).\n"
            report.append(error_message)
        else:
            state = f"La interfaz {interface} está operativa.\n"
            report.append(state)

    return report

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
        "3. /listar_dispositivos - Ver la lista de dispositivos disponibles."
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

# Iniciar el bot
bot.polling()