import configparser
from configparser import ConfigParser
from os import getpid, kill, makedirs, path, system
from signal import SIGTERM
from sys import argv, stderr
from threading import Thread
from time import sleep, time

from requests import RequestException
from telebot import TeleBot
from telebot.apihelper import (
    ApiTelegramException,
    _convert_list_json_serializable,
    _make_request,
)
from telebot.types import (
    BotCommand,
    BotCommandScope,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


def get_section_without_defaults(parser: ConfigParser, section: str) -> dict:
    # Extrae las opciones de una sección sin incluir los valores de la sección por defecto del 'ConfigParser'

    if parser.has_section(section):
        data = {
            item[0]: item[1]
            for item in parser.items(section)
            if item not in parser.items(parser.default_section)
            and not item[0].startswith("$")
        }

        return data

    return {}


def invert_dict_items(dict_like: dict) -> dict:
    # Invierte las claves a los valores y viceversa
    return {value: key for key, value in dict_like.items()}


def convert_values_to_int(dict_like: dict) -> dict:
    # Convierte todos los valores de un diccionario al tipo 'int'
    return dict(zip(dict_like.keys(), map(int, dict_like.values())))


class Colors:
    BLACK = "\x1b[30m"
    RED = "\x1b[31m"
    GREEN = "\x1b[32m"
    YELLOW = "\x1b[33m"
    BLUE = "\x1b[34m"
    MAGENTA = "\x1b[35m"
    CYAN = "\x1b[36m"
    WHITE = "\x1b[37m"
    RESET = "\x1b[39m"


class User:
    def __init__(self, one_pair_dict: dict):
        self.key = tuple(one_pair_dict.keys())[0]
        self.value = tuple(one_pair_dict.values())[0]


class Bot(TeleBot):
    __NAME_DATA_FOLDER = "TBC-data"
    __NAME_CONFIG_FILE = "tbc.ini"
    __NAME_BACKUP_FILE = "messages-backup.txt"
    __ABS_DATA_FOLDER = "{}/{}/".format(path.dirname(__file__), __NAME_DATA_FOLDER)
    __CONFIG_FILE = __ABS_DATA_FOLDER + __NAME_CONFIG_FILE
    __BACKUP_FILE = __ABS_DATA_FOLDER + __NAME_BACKUP_FILE

    def __init__(self, fast_init: bool = False, timeout: int = 10):
        self.config = ConfigParser()

        self.config.optionxform = lambda x: x

        self.load_config()

        super().__init__(self.apikey)

        if not fast_init:  # Solo para un uso extendido del programa.
            self.__next_message_is_cmd = False
            self.register_message_handler(self.__text_message, content_types=["text"])
            self.set_my_commands(
                [
                    BotCommand("start", "No hay nada que iniciar..."),
                    BotCommand("status", "Informa sobre algunos datos del bot."),
                    BotCommand("pc_control", "Algunos controles del PC."),
                    BotCommand("internet", "Herramientas de internet."),
                    BotCommand("help", "Información sobre como usar el bot."),
                ],
                timeout=timeout,
            )
            self.paperclip_on = False
            self.start_time = time()

    def set_my_commands(
        self,
        commands: list[BotCommand],
        scope: BotCommandScope | None = None,
        language_code: str | None = None,
        timeout: int = 15,
    ) -> bool:
        method_url = r"setMyCommands"

        params = {"commands": _convert_list_json_serializable(commands)}

        if scope:
            params["scope"] = scope.to_json()
        if language_code:
            params["language_code"] = language_code
        if timeout:
            params["timeout"] = timeout

        return _make_request(self.apikey, method_url, params=params, method="post")

    def load_config(self) -> None:
        try:
            c = self.config.read(self.__CONFIG_FILE)

        except configparser.DuplicateSectionError as e:
            stderr.write(
                "%serror%s [línea: %d]: sección '%s' duplicada en el archivo de configuración"
                % (Colors.RED, Colors.RESET, e.lineno, e.section)
            )
            exit(1)

        except configparser.DuplicateOptionError as e:
            stderr.write(
                "%serror%s [línea: %d]: opción '%s' duplicada en el archivo de configuración"
                % (Colors.RED, Colors.RESET, e.lineno, e.args[1])
            )
            exit(1)

        except (configparser.Error, configparser.MissingSectionHeaderError):
            stderr.write(
                "%serror%s: error al cargar el archivo de configuración\nmás información en el archivo README.md"
                % (Colors.RED, Colors.RESET)
            )
            exit(1)

        if len(c) > 0:
            ################# GET USERS ################

            try:
                self.users = invert_dict_items(
                    convert_values_to_int(self.config["USERS"])
                )
            except KeyError:
                self.users = {}

            ################# GET GROUPS ################

            try:
                self.groups = invert_dict_items(
                    convert_values_to_int(self.config["GROUPS"])
                )
            except KeyError:
                self.groups = {}

            ########## GET HIGH PRIVILEGE USER #########

            try:
                self.high = convert_values_to_int(self.config["HIGH"])
            except KeyError:
                self.high = {}

            ################ GET ALIASES ###############

            try:
                self.aliases = self.config["ALIASES"]
            except KeyError:
                self.aliases = {}

            try:
                ################ GET BOT API ###############

                bot_section = self.config["BOT"]

                ############# GET DEFAULT_TO VALUE #############

                default_user = self.config["DEFAULT_TO"]

            except KeyError as e:
                stderr.write(
                    "%serror%s: la sección '%s' no se encuentra en el archivo de configuración\nmás información en el archivo README.md"
                    % (Colors.RED, Colors.RESET, e.args[0])
                )
                exit(1)

            for section in (bot_section, default_user):
                if len(section) == 0:
                    stderr.write(
                        "%serror%s: sección '%s' vacía"
                        % (Colors.RED, Colors.RESET, section.name)
                    )
                    exit(1)

                elif len(section) > 1:
                    stderr.write(
                        "%serror%s: la sección '%s' debe contener un solo par 'clave = valor'"
                        % (Colors.RED, Colors.RESET, section.name)
                    )
                    exit(1)

            self.apikey = bot_section.get("apikey")

            if self.apikey is None:
                stderr.write(
                    "%serror%s: la sección 'BOT' debe contener una opción llamada 'apikey' conteniendo la API del Bot de Telegram"
                    % (Colors.RED, Colors.RESET)
                )
                exit(1)

            self.default_user = User(default_user)

        else:
            e = input("El archivo de configuración no existe! Desea crear uno? (Y/N) ")

            if e.lower().strip() == "y":
                self.create_config_file()

            exit(1)

    def save_config(self) -> None:
        with open(self.__CONFIG_FILE, "w") as config_file:
            self.config.write(config_file)

    def create_config_file(self):
        stderr.write(
            "%serror%s: función no implementada todavía" % (Colors.RED, Colors.RESET)
        )
        exit(1)

    @property
    def online_time(self) -> float:
        return time() - self.start_time

    def add_user_to_userlist(self, user_name, user_id) -> None:
        self.users[user_id] = user_name
        self.config["USERS"][user_name] = str(user_id)

    def add_group_to_grouplist(self, group_name, group_id) -> None:
        self.groups[group_id] = group_name
        self.config["GROUPS"][group_name] = str(group_id)

    def __text_message(self, message) -> None:
        # SECCIÓN DE MENSAJE ENTRANTE

        from_ = ""

        if (
            message.json["chat"]["type"] == "group"
        ):  # Si es un mensaje que proviene de un grupo.
            group_name, group_id = (
                message.json["chat"]["title"],
                message.json["chat"]["id"],
            )

            if (
                message.json["chat"]["id"] in self.groups.keys()
            ):  # Si es un grupo conocido, obtener su nombre.
                group_name = self.groups[group_id]

            self.add_group_to_grouplist(group_name, group_id)
            from_ += group_name + "/"

        user_name, user_id = (
            message.json["from"]["first_name"],
            message.json["from"]["id"],
        )

        if (
            user_id in self.users.keys()
        ):  # Si es un usuario conocido, obtener su nombre.
            user_name = self.users[user_id]

        else:  # Si no, asignarle el nombre "UNKNOWN_%(nombre de usuario)s_%(id)d" y añadirlo a los usuarios conocidos
            user_name = "UNKNOWN_%s_%d" % (user_name, user_id)
            self.add_user_to_userlist(user_name, user_id)

        from_ += user_name

        # IMPRIMR Y GUARDAR EL MENSAJE DEL USUARIO
        mensaje_del_usuario = "[%s]: %s" % (from_, message.json["text"])

        self.print_and_save(
            mensaje_del_usuario,
            reset_input=(
                False if message.json["text"] == "/quit" or self.paperclip_on else True
            ),
            new_line_before=not self.paperclip_on,
            new_line_after=self.paperclip_on,
        )

        if self.__next_message_is_cmd and (
            message.json["text"]
            in [
                "Close Session",
                "Lock Session",
                "Restart",
                "Shutdown",
                "Logout",
                "Logout and Shutdown",
            ]
        ):
            self.__check_special_message(message)

        self.__next_message_is_cmd = False

        # SECCIÓN DE RESPUESTA
        respuesta_bot, reply_markup = None, ReplyKeyboardRemove()

        if message.json["text"] == "/start":
            respuesta_bot = "No hay nada que iniciar zopenco."

        elif message.json["text"] == "/status":
            respuesta_bot = "El bot lleva activo %d segundos" % round(self.online_time)

        elif message.json["text"] == "/help":
            respuesta_bot = "Solo escríbeme, ya te contestaré cuando pueda..."

        elif message.json["text"] in ["/pc_control", "/internet"]:
            respuesta_bot = "No tienes acceso a esa opción."

            if user_id in self.high.values():
                botones = ReplyKeyboardMarkup()

                if message.json["text"] == "/pc_control":
                    botones.add(
                        KeyboardButton("Close Session"),
                        KeyboardButton("Lock Session"),
                        KeyboardButton("Restart"),
                        KeyboardButton("Shutdown"),
                    )

                elif message.json["text"] == "/internet":
                    botones.add(
                        KeyboardButton("Logout"),
                        KeyboardButton("Logout and Shutdown"),
                        row_width=1,
                    )

                respuesta_bot = "Elige la opción..."
                reply_markup = botones
                self.__next_message_is_cmd = True

        elif message.json["text"] == "/quit":
            respuesta = "Apagando el bot..."

            self.print_and_save(respuesta, reset_input=False)
            self.save_config()

            kill(getpid(), SIGTERM)
            return 0

        if respuesta_bot:
            self.reply_to(message, respuesta_bot, reply_markup=reply_markup)

            self.print_and_save("Bot: %s" % respuesta_bot)

    def __check_special_message(self, message) -> None:
        options = {
            "Close Session": ["shutdown /l", "Sesión Cerrada"],
            "Lock Session": [
                "rundll32.exe user32.dll, LockWorkStation",
                "Sesión Bloqueada",
            ],
            "Restart": ["shutdown /r", "Reiniciando PC ..."],
            "Shutdown": ["shutdown /p", "Apagando PC ..."],
            "Logout": [
                "login.py lo",
                "Cerrando sesión ...",
            ],  # this is a specific case for each user, first arg is the comand line way to close the internet access
            "Logout and Shutdown": ["Cerrando sesión ...", "Apagando PC ..."],
        }

        if message.json["from"]["id"] in self.high.values():
            if message.json["text"] == "Logout and Shutdown":
                text = "Cerrando sesión y apagando PC ..."

                self.reply_to(message, text, reply_markup=ReplyKeyboardRemove())
                self.print_and_save("Bot: %s" % text)

                system(options["Logout"][0])
                system(options["Shutdown"][0])
                return 0

            cmd = options[message.json["text"]][0]
            text = options[message.json["text"]][1]

        else:
            cmd = ""
            text = "No tienes acceso a esa opción."

        self.reply_to(message, text, reply_markup=ReplyKeyboardRemove())
        self.print_and_save("Bot: %s" % text)
        system(cmd)

    def send_message(self, *args, **kwargs) -> int:
        try:
            self.print_and_save(args[1], print_message=False)
            super().send_message(*args, **kwargs)
            return 0

        except ApiTelegramException as e:
            if e.description == "Forbidden: bot was blocked by the user":
                stderr.write(
                    "%serror%s: mensaje no enviado. Razón: El usuario '%s' ha bloqueado el bot."
                    % (Colors.RED, Colors.RESET, self.users[args[0]])
                )

            else:
                stderr.write(
                    "%serror%s: %s" % (Colors.RED, Colors.RESET, e.description)
                )

        except RequestException:
            stderr.write(
                "%serror%s: no se pudo enviar el mensaje, compruebe su conexión a internet o cortafuegos"
                % (Colors.RED, Colors.RESET)
            )

        return 1

    def match_user_by_first_letter(self, to_match) -> tuple[int, str]:
        def starts_with_that(x):
            return to_match.lower().startswith("/{} ".format(x.lower()))

        in_aliases = any(map(starts_with_that, self.config["ALIASES"].keys()))
        in_users = any(map(starts_with_that, self.config["USERS"].keys()))

        if in_aliases or in_users:
            thing = to_match.split()
            initial, texto = thing[0], " ".join(thing[1:])
            section = "USERS" if in_users else "ALIASES"
            return int(self.config[section][initial.strip("/ ")]), texto

        else:
            in_aliases = to_match.strip("/ ") in self.config["ALIASES"].keys()
            in_users = to_match.strip("/ ") in self.config["USERS"].keys()

            if in_users:
                return int(self.config["USERS"][to_match.strip("/ ")]), ""

            elif in_aliases:
                return (
                    int(
                        self.config["USERS"][
                            self.config["ALIASES"][to_match.strip("/ ")]
                        ]
                    ),
                    "",
                )
            else:
                return 0, ""

    def print_and_save(
        self,
        message,
        print_message=True,
        reset_input=True,
        new_line_before=True,
        new_line_after=False,
    ):
        makedirs(self.__ABS_DATA_FOLDER, exist_ok=True)

        (
            print(
                "%s%s%s%s"
                % (
                    "\n" if new_line_before else "",
                    message,
                    "\n-> " if reset_input else "",
                    "\n" if new_line_after else "",
                ),
                end="",
                flush=True,
            )
            if print_message
            else None
        )

        try:
            file = open(self.__BACKUP_FILE, "a", encoding="utf-8")

        except FileNotFoundError:
            file = open(self.__BACKUP_FILE, "w", encoding="utf-8")

        file.write(message + "\n")
        file.close()

    def __del__(self):
        self.save_config()


def listener_thread(bot):
    try:
        bot.infinity_polling(60)

    except Exception as e:
        print(e)


def main() -> int:
    if len(argv) == 1:
        try:
            bot = Bot(timeout=5)

        except RequestException:
            stderr.write(
                "%serror%s: compruebe su conexión a internet o cortafuegos"
                % (Colors.RED, Colors.RESET)
            )

            exit(1)

        t1 = Thread(target=listener_thread, kwargs={"bot": bot}, daemon=True)
        t1.start()

        last_id, id = bot.default_user.value, bot.default_user.value

        try:
            while True:
                if last_id != id:
                    print("Usuario cambiado a: %s" % bot.users[id].capitalize())
                    last_id = id

                entrada = input("-> ").strip()

                # Cerrar el bot
                if entrada in ["/quit", "/q", "q", "/exit"]:
                    respuesta = "Apagando el bot..."

                    bot.save_config()
                    bot.print_and_save(respuesta, print_message=False)

                    break

                # Verificar si se desea cambiar de usuario
                elif (int_str := bot.match_user_by_first_letter(entrada))[0]:
                    id, entrada = int_str

                # Enviar el contenido de un archivo
                elif entrada in ["/file", "/archivo"]:
                    entrada = input("Ingrese la ruta del archivo: ")

                    if entrada == "":
                        print("Continuando...")

                    else:
                        try:
                            with open(entrada, "r") as file:
                                entrada = file.read()

                        except FileNotFoundError:
                            print("Archivo no encontrado")
                            continue

                # Mostrar por consola el tiempo que el bot lleva activo
                elif entrada in ["/status", "status", "/estado", "estado"]:
                    print("El bot lleva activo %d segundos" % round(bot.online_time))
                    continue

                # Mostrar por consola la lista de todos los usuarios registrados
                elif entrada in ["/listausuarios", "/usuarios", "/lista_usuarios"]:
                    for key, value in zip(bot.users.keys(), bot.users.values()):
                        print("%s: %d" % (key, value))
                    continue

                # Enviar al bot todo lo que se copie en el portapapeles
                elif entrada in ["/clipboard", "/portapapeles", "/cp"]:
                    print(
                        "Iniciando copiadora de portapapeles... (Presione consecutivamente las letras 'q', 'w' y 'e' para terminar)"
                    )

                    from pynput import keyboard
                    from pyperclip import copy, paste

                    bot.paperclip_on = True
                    copy("")
                    keys_pressed_pool = []

                    def press(key):
                        global keys_pressed_pool

                        try:
                            key = key.char
                            keys_pressed_pool.append(key)

                            if len(keys_pressed_pool) > 3:
                                keys_pressed_pool.pop(0)

                        except BaseException:
                            pass

                        if keys_pressed_pool == ["q", "w", "e"]:
                            bot.paperclip_on = False
                            return False

                    t2 = keyboard.Listener(on_press=press)
                    t2.start()

                    while True:
                        if not bot.paperclip_on:
                            print(
                                "Abortando. Continuando la ejecución del programa principal..."
                            )
                            break

                        sleep(0.01)

                        content = paste()

                        if content:
                            bot.send_message(id, content)
                            bot.print_and_save(
                                "Portapapeles: " + content,
                                print_message=True,
                                reset_input=False,
                                new_line_before=False,
                                new_line_after=True,
                            )

                            copy("")

                    continue

                if entrada:
                    bot.send_message(id, entrada)

        except KeyboardInterrupt:
            print("\nApagando el bot...")
            bot.save_config()

    else:
        messages = argv[1:]

        try:
            bot = Bot(fast_init=True, timeout=5)

        except RequestException:
            stderr.write(
                "%serror%s: compruebe su conexión a internet o cortafuegos"
                % (Colors.RED, Colors.RESET)
            )

            exit(1)

        for message in messages:
            bot.print_and_save(message, print_message=False)
            status_code = bot.send_message(bot.default_user.value, message)

            if status_code != 0:
                exit(status_code)

        print("Done! (Sent %d messages)" % len(messages))

    return 0


if __name__ == "__main__":
    main()
