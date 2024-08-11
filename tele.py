from time import time, sleep
from threading import Thread
from signal import SIGTERM
from os import makedirs, kill, system, getpid
from configparser import ConfigParser
from sys import argv
from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from requests import RequestException

def print_and_save(message, file_route, print_message=True, reset_input=True, new_line_before=True, new_line_after=False):
    file_route =  file_route if '\\' not in file_route else file_route.replace('\\', '/')
    folder = '/'.join(file_route.split('/')[:-1])
    makedirs(folder, exist_ok=True)
    print('%s%s%s%s'%('\n' if new_line_before else '',
                    message,
                    '\n-> ' if reset_input else '', 
                    '\n' if new_line_after else ''), end='', flush=True) if print_message else None
    try:
        file =  open(file_route, 'a', encoding='utf-8')
    except FileNotFoundError:
        file =  open(file_route, 'w', encoding='utf-8')
    file.write(message + '\n')
    file.close()

def get_section_without_defaults(parser:ConfigParser, section:str) -> dict:
    if parser.has_section(section):
        data = {item[0]:item[1] for item in parser.items(section) if item not in parser.items(parser.default_section) and not item[0].startswith('$')}
        return data
    return {}

class Bot(TeleBot):
    name_folder = 'TBC-data'
    name_file_backup = 'messages-backup.txt'
    name_file_config = 'tbc.ini'
    script_route = '/'.join(__file__.split('\\')[:-1]) + '/'
    abs_folder = script_route + name_folder + '/'
    abs_file_backup = abs_folder + name_file_backup
    abs_file_config = abs_folder + name_file_config

    def __init__(self, fast_init:bool=False):
        self.config = ConfigParser()
        self.load_config()
        super().__init__(self.apikey)
        if not fast_init: # Only meant for extended use of the bot.
            self.__next_message_is_cmd = False
            self.users_ = {value:key for key, value in zip(self.users.keys(), self.users.values())}
            self.register_message_handler(self.__text_message, content_types=['text'])
            self.set_my_commands(
                [BotCommand('start', 'No hay nada que iniciar...'),
                BotCommand('status', 'Informa sobre algunos datos del bot.'),
                BotCommand('pc_control', 'Algunos controles del PC.'),
                BotCommand('internet', 'Herramientas de internet.'),
                BotCommand('help', 'Información sobre como usar el bot.')])
            self.paperclip_on, self.desconocido_counter = False, 0
            self.start_time = time()

    def load_config(self) -> None:
        c = self.config.read(self.abs_file_config)
        if len(c) > 0:
            convert_values_to_int = lambda dict_: dict(zip(dict_.keys(), map(int, dict_.values()))) # Converts all values of a dictionary to type int
            ################# GET USERS ################
            try:
                self.users = convert_values_to_int(self.config['USERS'])
            except KeyError:
                self.users = {}
            ########## GET HIGH PRIVILEGE USER #########
            try:
                self.high = convert_values_to_int(self.config['HIGH'])
            except KeyError:
                self.high = {}
            ################ GET ALIASES ###############    
            try:
                self.aliases = self.config['ALIASES']
            except KeyError:
                self.aliases = {}
            try:
            ################ GET BOT API ###############
                self.apikey = self.config['BOT']['apikey']
            ############# GET DEFAULT USER #############
                default_user = self.config['DEFAULT_USER']
                if len(default_user) > 1:            
                    raise Exception('Section DEFAULT_USER can only contain one value')
                self.default_user = int(list(default_user.values())[0])
            except KeyError as e:
                e.args = ('There is no section {} in the config file. Create one and try again.'.format(e.args[0]),)
                e.add_note('More info at README.md')
                raise e
            ############################################
        else:
            e = input('El archivo de configuración no existe! Desea crear uno? (Y/N) ')
            if e.lower().strip() == 'y':
                self.create_config_file()
            exit(1)

    def save_config(self) -> None:
        with open(self.abs_file_config, 'w') as config_file:
            self.config.write(config_file)
    
    def create_config_file(self):
        raise Exception('Not implemented!')

    @property
    def online_time(self) -> float:
        return time()-self.start_time

    def __text_message(self, message) -> None:
        # SECCIÓN DE MENSAJE ENTRANTE
        if message.chat.id in self.users_.keys():  # Si es un usuario conocido, obtener su nombre.
            name_of_user = self.users_[message.chat.id]
        else:                                      # Si no, asignarle el nombre "UNKNOWN_(número) - (nombre de usuario)" y añadirlo a los usuarios conocidos
            self.desconocido_counter += 1
            name_of_user = message.json["from"]["first_name"]
            name_of_user = 'UNKNOWN_%d - %s'%(self.desconocido_counter, name_of_user)
            self.users[name_of_user] = message.chat.id
            self.users_[message.chat.id] = name_of_user
        
        # IMPRIMR Y GUARDAR EL MENSAJE DEL USUARIO
        mensaje_del_usuario = '%s - %d: %s'%(name_of_user, message.chat.id, message.text)
        print_and_save(mensaje_del_usuario, self.abs_file_backup, reset_input=False if message.text == '/quit' or self.paperclip_on else True, new_line_before=not self.paperclip_on, new_line_after=self.paperclip_on)
        
        # SECCIÓN DE RESPUESTA
        respuesta_bot, reply_markup = None, ReplyKeyboardRemove()
        if message.text == '/start':
            respuesta_bot = 'No hay nada que iniciar zopenco.'
        elif message.text == '/status':
            respuesta_bot = 'El bot lleva activo %d segundos'%round(self.online_time)
        elif message.text == '/help':
            respuesta_bot = 'Solo escríbeme, ya te contestaré cuando pueda...'
        elif message.text == '/quit':
            respuesta = 'Apagando el bot...'
            print_and_save(respuesta, self.abs_file_backup, reset_input=False)
            self.save_config()
            kill(getpid(), SIGTERM)
            return 0
        elif message.text in ['/pc_control', '/internet']:
            respuesta_bot = 'No tienes acceso a esa opción.'
            if message.chat.id in self.high:
                botones = ReplyKeyboardMarkup()
                if message.text == '/pc_control':
                    close_session_button, lock_button, restart_button, shutdown_button = KeyboardButton('Close Session'), KeyboardButton('Lock Session'), KeyboardButton('Restart'), KeyboardButton('Shutdown')
                    botones.add(close_session_button, lock_button, restart_button, shutdown_button)
                elif message.text == '/internet':
                    login, logout, logout_shutdown = KeyboardButton('Login'), KeyboardButton('Logout'), KeyboardButton('Logout and Shutdown')
                    botones.add(#login, 
                                logout, logout_shutdown, row_width=1)
                respuesta_bot = 'Elige la opción...'
                reply_markup = botones
        elif self.__next_message_is_cmd and (message.text in ['Close Session', 'Lock Session', 'Restart', 'Shutdown', 'Login', 'Logout', 'Logout and Shutdown']):
            self.__check_special_message(message)
        if respuesta_bot:
            self.reply_to(message, respuesta_bot, reply_markup=reply_markup)
            mensaje_del_bot = 'Bot: %s'%respuesta_bot
            print_and_save(mensaje_del_bot, self.abs_file_backup)
        self.__next_message_is_cmd = True if (message.text == '/pc_control' or message.text == '/internet') and (message.chat.id in self.high) else False

    def __check_special_message(self, message):
        options = {
                'Close Session': ['shutdown /l', 'Sesión Cerrada'],
                'Lock Session': ['rundll32.exe user32.dll, LockWorkStation', 'Sesión Bloqueada'],
                'Restart': ['shutdown /r', 'Reiniciando PC ...'],
                'Shutdown': ['shutdown /p', 'Apagando PC ...'],
                #'Login': ['login.py l', 'Iniciando sesión ...'],
                'Logout': ['login.py lo', 'Cerrando sesión ...'],
                'Logout and Shutdown': ['Cerrando sesión ...', 'Apagando PC ...'],
                }
        if message.text == 'Logout and Shutdown':
            text = 'Cerrando sesión y apagando PC ...'
            self.reply_to(message, text, reply_markup=ReplyKeyboardRemove())
            print_and_save('Bot: %s'%text, self.abs_file_backup)
            system(options['Logout'][0])
            system(options['Shutdown'][0])
            return 0
        
        cmd = options[message.text][0] if message.chat.id in self.high else ''
        text = options[message.text][1] if message.chat.id in self.high else 'No tienes acceso a esa opción.'
        self.reply_to(message, text, reply_markup=ReplyKeyboardRemove())
        print_and_save('Bot: %s'%text, self.abs_file_backup)
        system(cmd)

def listener_thread(bot):
    try:
        bot.infinity_polling(60)
    except Exception as e:
        print(e)

def send_message(bot, id, message) -> int:
    try:
        print_and_save(message, bot.abs_file_backup, print_message=False)
        bot.send_message(id, message)
        return 0
    except ApiTelegramException as e:
        if e.description == 'Forbidden: bot was blocked by the user':
            print('Mensaje no enviado. Razón: El usuario -> %s <- ha bloqueado el bot.'%(bot.users_[id]))
        else:
            print(e)
    except RequestException:
        print('Error al enviar el mensaje. Inténtelo denuevo.')
    return 1

def match_user_by_first_letter(bot, to_match) -> tuple[int, str]:
    starts_with_that = lambda x: to_match.lower().startswith('/{} '.format(x.lower()))
    in_aliases = any(map(starts_with_that, bot.config['ALIASES'].keys()))
    in_users = any(map(starts_with_that, bot.config['USERS'].keys()))
    if in_aliases or in_users:
        thing = to_match.split()
        initial, texto = thing[0], ' '.join(thing[1:])
        section = 'USERS' if in_users else 'ALIASES'
        return int(bot.config[section][initial.strip('/ ')]), texto
    else:
        in_aliases = to_match.strip('/ ') in bot.config['ALIASES'].keys()
        in_users = to_match.strip('/ ') in bot.config['USERS'].keys()
        if in_users:
            return int(bot.config['USERS'][to_match.strip('/ ')]), ''
        elif in_aliases:
            return int(bot.config['USERS'][bot.config['ALIASES'][to_match.strip('/ ')]]), ''
        else:
            return 0, ''

def main() -> int:
    if len(argv) == 1:
        try:
            bot = Bot()
        except Exception as e:
            raise e
        t1 = Thread(target=listener_thread, kwargs={'bot':bot}, daemon=True)
        t1.start()
        last_id, id = bot.default_user, bot.default_user
        notify = lambda:print('Usuario cambiado a: %s'%bot.users_[id].capitalize())
        try:
            while True:
                if last_id!=id:
                    notify()
                    last_id = id
                entrada = input('-> ')
                # Cerrar el bot
                if entrada in ['/quit', '/q', 'q', '/exit']:
                    respuesta = 'Apagando el bot...'
                    bot.save_config()
                    print_and_save(respuesta, bot.abs_file_backup, print_message=False)
                    break
                # Verificar si se desea cambiar de usuario
                elif (int_str:=match_user_by_first_letter(bot, entrada))[0]:
                    id, entrada = int_str
                # Enviar el contenido de un archivo
                elif entrada in ['/file', '/archivo']:
                    entrada = input('Ingrese la ruta del archivo: ')
                    if entrada == '':
                        print('Continuando...')
                    else:
                        try:
                            with open(entrada, 'r') as file:
                                entrada = file.read()
                        except FileNotFoundError:
                            print('Archivo no encontrado')
                            continue
                # Mostrar por consola el tiempo que el bot lleva activo
                elif entrada in ['/status', 'status', '/estado', 'estado']:
                    print('El bot lleva activo %d segundos'%round(bot.online_time))
                    continue
                # Mostrar por consola la lista de todos los usuarios registrados
                elif entrada in ['/listausuarios', '/usuarios', '/lista_usuarios']:
                    for key, value in zip(bot.users.keys(), bot.users.values()):
                        print('%s: %d'%(key,value))
                    continue
                # Enviar al bot todo lo que se copie en el portapapeles
                elif entrada in ['/clipboard', '/portapapeles', '/cp']:
                    print('Iniciando copiadora de portapapeles... (Presione consecutivamente las letras \'q\', \'w\' y \'e\' para terminar)')
                    from pyperclip import copy, paste
                    from pynput import keyboard
                    bot.paperclip_on = True
                    copy('')
                    keys_pressed_pool = []
                    def press(key):
                        global keys_pressed_pool
                        try:
                            key = key.char
                            keys_pressed_pool.append(key)
                            if len(keys_pressed_pool) > 3:
                                keys_pressed_pool.pop(0)
                        except:
                            pass
                        if keys_pressed_pool == ['q', 'w', 'e']:
                            bot.paperclip_on = False
                            return False
                    t2 = keyboard.Listener(on_press=press)
                    t2.start()
                    while True:
                        if not bot.paperclip_on:
                            print('Abortando. Continuando la ejecución del programa principal...')
                            break
                        sleep(0.01)
                        content = paste()
                        if content:
                            send_message(bot, id, content)
                            print_and_save('Portapapeles: '+content,
                                           bot.abs_file_backup,
                                           print_message=True,
                                           reset_input=False,
                                           new_line_before=False,
                                           new_line_after=True
                                           )
                            copy('')
                    continue
                if entrada:
                    send_message(bot, id, entrada)
        except KeyboardInterrupt:
            print('\nApagando el bot...')
            bot.save_config()
    else:
        messages = argv[1:]
        bot = Bot(fast_init=True)
        for message in messages:
            print_and_save(message, bot.abs_file_backup, print_message=False)
            send_message(bot, bot.users['Raidel'], message)
        print('Done! (Sent %d messages)'%len(messages))
    return 0

if __name__ == '__main__':
    main()