"""The top level of the ASN.1 tools package contains commonly used
functions and classes, and the command line interface.

"""

import sys
import os
import argparse
import binascii
import logging

from prompt_toolkit.contrib.completers import WordCompleter
from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.interface import AbortAction
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

from .compiler import compile_dict
from .compiler import compile_string
from .compiler import compile_files
from .compiler import pre_process_dict
from .parser import parse_string
from .parser import parse_files
from .parser import ParseError
from .errors import Error
from .errors import EncodeError
from .errors import DecodeError
from .errors import CompileError
from .errors import ConstraintsError


__author__ = 'Erik Moqvist'
__version__ = '0.80.1'


class ArgumentParserError(Error):
    pass


class ArgumentParser(argparse.ArgumentParser):

    def exit(self, status=0, message=None):
        if message:
            self._print_message(message, sys.stdout)

        raise ArgumentParserError(message)

    def error(self, message):
        self.print_usage(sys.stdout)
        message = '{}: error: {}'.format(self.prog, message)
        print(message)

        raise ArgumentParserError(message)


def _convert_hexstring(input_spec,
                       output_spec,
                       output_codec,
                       type_name,
                       hexstring):
    try:
        encoded = binascii.unhexlify(hexstring)
    except Exception as e:
        raise TypeError("'{}': {}".format(hexstring, str(e)))

    decoded = input_spec.decode(type_name, encoded)

    if output_codec in ['gser', 'xer', 'jer']:
        decoded = output_spec.encode(type_name, decoded, indent=4).strip()
    else:
        decoded = binascii.hexlify(output_spec.encode(type_name, decoded))

    print(decoded.decode('latin-1'))


def _compile_files(specifications, input_codec, output_codec):
    parsed = parse_files(specifications)
    input_spec = compile_dict(parsed, input_codec)
    output_spec = compile_dict(parsed, output_codec)

    return input_spec, output_spec


def _do_convert(args):
    input_spec, output_spec = _compile_files(args.specification,
                                             args.input_codec,
                                             args.output_codec)

    if args.hexstring == '-':
        for hexstring in sys.stdin:
            hexstring = hexstring.strip('\r\n')

            if hexstring:
                try:
                    _convert_hexstring(input_spec,
                                       output_spec,
                                       args.output_codec,
                                       args.type,
                                       hexstring)
                except TypeError:
                    print(hexstring)
                except DecodeError as e:
                    print(hexstring)
                    print(str(e))
            else:
                print(hexstring)
    else:
        _convert_hexstring(input_spec,
                           output_spec,
                           args.output_codec,
                           args.type,
                           args.hexstring)


def _handle_command_compile(line):
    parser = ArgumentParser(prog='compile')
    parser.add_argument('-i', '--input-codec',
                        choices=('ber', 'der', 'jer', 'per', 'uper', 'xer'),
                        default='ber',
                        help='Input codec (default: ber).')
    parser.add_argument('-o', '--output-codec',
                        choices=('ber', 'der', 'jer', 'per', 'uper', 'xer', 'gser'),
                        default='gser',
                        help='Output codec (default: gser).')
    parser.add_argument('specification',
                        nargs='+',
                        help='ASN.1 specification as one or more .asn files.')

    try:
        args = parser.parse_args(args=line.split()[1:])
    except ArgumentParserError:
        return None, None, None

    try:
        input_spec, output_spec = _compile_files(args.specification,
                                                 args.input_codec,
                                                 args.output_codec)
        return input_spec, output_spec, args.output_codec
    except Exception as e:
        print('error: {}'.format(str(e)))
        return None, None, None


def _handle_command_convert(line, input_spec, output_spec, output_codec):
    if not input_spec:
        print("No compiled specification found. Please use the "
              "'compile' command to compile one.")
        return

    parser = ArgumentParser(prog='convert')
    parser.add_argument('type', help='Type to convert.')
    parser.add_argument(
        'hexstring',
        help='Hexstring to convert.')

    try:
        args = parser.parse_args(args=line.split()[1:])
    except ArgumentParserError:
        return

    try:
        _convert_hexstring(input_spec,
                           output_spec,
                           output_codec,
                           args.type,
                           args.hexstring)
    except Exception as e:
        print('error: {}'.format(str(e)))


def _handle_command_help():
    print('Commands:')
    print('  compile')
    print('  convert')
    print('  exit')
    print('  help')


def _do_shell(_args):
    commands = ['compile', 'convert', 'help', 'exit']
    completer = WordCompleter(commands, WORD=True)
    user_home = os.path.expanduser('~')
    history = FileHistory(os.path.join(user_home, '.asn1tools-history.txt'))
    input_spec = None
    output_spec = None
    output_codec = None

    print("\nWelcome to the asn1tools shell!\n")

    while True:
        try:
            line = prompt(u'$ ',
                          completer=completer,
                          complete_while_typing=True,
                          auto_suggest=AutoSuggestFromHistory(),
                          enable_history_search=True,
                          history=history,
                          on_abort=AbortAction.RETRY)
        except EOFError:
            return

        line = line.strip()

        if line:
            if line.startswith('compile'):
                input_spec, output_spec, output_codec = _handle_command_compile(line)
            elif line.startswith('convert'):
                _handle_command_convert(line,
                                        input_spec,
                                        output_spec,
                                        output_codec)
            elif line == 'help':
                _handle_command_help()
            elif line == 'exit':
                return
            else:
                print('{}: command not found'.format(line))


def _main():
    parser = argparse.ArgumentParser(
        description='Various ASN.1 utilities.')

    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('-v', '--verbose',
                        choices=(0, 1, 2),
                        type=int,
                        default=1,
                        help=('Control the verbosity; disable(0), warning(1) '
                              'and debug(2). (default: 1).'))
    parser.add_argument('--version',
                        action='version',
                        version=__version__,
                        help='Print version information and exit.')

    # Workaround to make the subparser required in Python 3.
    subparsers = parser.add_subparsers(title='subcommands',
                                       dest='subcommand')
    subparsers.required = True

    # The 'convert' subparser.
    subparser = subparsers.add_parser(
        'convert',
        description='Convert given hextring and print it to standard output.')
    subparser.add_argument('-i', '--input-codec',
                           choices=('ber', 'der', 'jer', 'per', 'uper', 'xer'),
                           default='ber',
                           help='Input format (default: ber).')
    subparser.add_argument('-o', '--output-codec',
                           choices=('ber', 'der', 'jer', 'per', 'uper', 'xer', 'gser'),
                           default='gser',
                           help='Output format (default: gser).')
    subparser.add_argument('specification',
                           nargs='+',
                           help='ASN.1 specification as one or more .asn files.')
    subparser.add_argument('type', help='Type to convert.')
    subparser.add_argument(
        'hexstring',
        help='Hexstring to convert, or - to read hexstrings from standard input.')
    subparser.set_defaults(func=_do_convert)

    # The 'shell' subparser.
    shell_parser = subparsers.add_parser('shell',
                                         description='An interactive shell.')
    shell_parser.set_defaults(func=_do_shell)

    args = parser.parse_args()

    levels = [logging.CRITICAL, logging.WARNING, logging.DEBUG]
    level = levels[args.verbose]

    logging.basicConfig(format='%(levelname)s: %(message)s',
                        level=level)

    if args.debug:
        args.func(args)
    else:
        try:
            args.func(args)
        except BaseException as e:
            sys.exit('error: {}'.format(str(e)))
