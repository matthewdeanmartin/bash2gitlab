# """Example integration of InputChangeDetector with run_compile_all function."""
#
# from pathlib import Path
# import logging
# from bash2gitlab.commands.input_change_detector import InputChangeDetector, needs_compilation, mark_compilation_complete
#
# logger = logging.getLogger(__name__)


# # Command line integration example
# def add_change_detection_args(parser):
#     """Add change detection arguments to argument parser."""
#     parser.add_argument(
#         '--force',
#         action='store_true',
#         help='Force compilation even if no input changes detected'
#     )
#     parser.add_argument(
#         '--check-only',
#         action='store_true',
#         help='Only check if compilation is needed, do not compile'
#     )
#     parser.add_argument(
#         '--list-changed',
#         action='store_true',
#         help='List files that have changed since last compilation'
#     )
#
#
# def handle_change_detection_commands(args, uncompiled_path: Path) -> bool:
#     """Handle change detection specific commands. Returns True if command was handled."""
#
#     if args.check_only:
#         if needs_compilation(uncompiled_path):
#             print("Compilation needed: input files have changed")
#             return True
#         else:
#             print("No compilation needed: no input changes detected")
#             return True
#
#     if args.list_changed:
#         from bash2gitlab.commands.input_change_detector import get_changed_files
#         changed = get_changed_files(uncompiled_path)
#         if changed:
#             print("Changed files since last compilation:")
#             for file_path in changed:
#                 print(f"  {file_path}")
#         else:
#             print("No files have changed since last compilation")
#         return True
#
#     return False
