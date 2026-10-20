"""Select the desktop startup mode without an extra selection dialog."""
def add_launch_arguments(parser):
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--local', dest='launch_mode', action='store_const', const='demo',
                       help='Run the teacher and student windows on this computer')
    modes.add_argument('--lan', dest='launch_mode', action='store_const', const='lan',
                       help='Configure a server or workstation on the local network')


def launch_mode(args):
    # Keep the older classroom configuration shortcut compatible.
    return args.launch_mode or ('lan' if args.configure_classroom else 'demo')


def startup_config(data, mode, setup, force=False):
    return {'demo': True} if mode == 'demo' else setup(data, force=force)
