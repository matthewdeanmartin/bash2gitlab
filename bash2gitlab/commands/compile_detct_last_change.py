# """Example integration of InputChangeDetector with run_compile_all function."""
#
# from pathlib import Path
# import logging
# from bash2gitlab.commands.input_change_detector import InputChangeDetector, needs_compilation, mark_compilation_complete
#
# logger = logging.getLogger(__name__)
#
#
# def run_compile_all(
#         uncompiled_path: Path,
#         output_path: Path,
#         dry_run: bool = False,
#         parallelism: int | None = None,
#         force: bool = False,  # New parameter to force compilation
# ) -> int:
#     """
#     Main function to process a directory of uncompiled GitLab CI files.
#     Now includes input change detection for efficient incremental builds.
#
#     Args:
#         uncompiled_path (Path): Path to the input .gitlab-ci.yml, other yaml and bash files.
#         output_path (Path): Path to write the .gitlab-ci.yml file and other yaml.
#         dry_run (bool): If True, simulate the process without writing any files.
#         parallelism (int | None): Maximum number of processes to use for parallel compilation.
#         force (bool): If True, force compilation even if no input changes detected.
#
#     Returns:
#         The total number of inlined sections across all files.
#     """
#
#     # Check if compilation is needed (unless forced)
#     if not force:
#         if not needs_compilation(uncompiled_path):
#             logger.info("No input changes detected since last compilation. Skipping compilation.")
#             logger.info("Use --force to compile anyway, or modify input files to trigger compilation.")
#             return 0
#         else:
#             logger.info("Input changes detected, proceeding with compilation...")
#
#     # ... existing code for strays check ...
#     strays = report_targets(output_path)
#     if strays:
#         print("Stray files in output folder, halting")
#         for stray in strays:
#             print(f"  {stray}")
#         sys.exit(200)
#
#     total_inlined_count = 0
#     written_files_count = 0
#
#     if not dry_run:
#         output_path.mkdir(parents=True, exist_ok=True)
#
#     # ... rest of existing compilation logic ...
#
#     # Your existing code here for processing files
#     # global_vars_path = uncompiled_path / "global_variables.sh"
#     # ... etc ...
#
#     # After successful compilation, mark as complete
#     if not dry_run and (total_inlined_count > 0 or written_files_count > 0):
#         try:
#             mark_compilation_complete(uncompiled_path)
#             logger.debug("Marked compilation as complete - updated input file hashes")
#         except Exception as e:
#             logger.warning(f"Failed to update input hashes: {e}")
#
#     if written_files_count == 0 and not dry_run:
#         logger.warning(
#             "No output files were written. This could be because all files are up-to-date, or due to errors."
#         )
#     elif not dry_run:
#         logger.info(f"Successfully processed files. {written_files_count} file(s) were created or updated.")
#     elif dry_run:
#         logger.info(f"[DRY RUN] Simulation complete. Would have processed {written_files_count} file(s).")
#
#     return total_inlined_count
#
#
# # Alternative: More granular approach for processing individual files
# def run_compile_all_granular(
#         uncompiled_path: Path,
#         output_path: Path,
#         dry_run: bool = False,
#         parallelism: int | None = None,
#         force: bool = False,
# ) -> int:
#     """
#     Alternative implementation with per-file change detection.
#     This allows skipping individual files that haven't changed.
#     """
#
#     detector = InputChangeDetector(uncompiled_path)
#
#     # Clean up stale hashes first
#     detector.cleanup_stale_hashes(uncompiled_path)
#
#     total_inlined_count = 0
#     written_files_count = 0
#
#     # ... existing setup code ...
#
#     if uncompiled_path.is_dir():
#         template_files = list(uncompiled_path.rglob("*.yml")) + list(uncompiled_path.rglob("*.yaml"))
#         if not template_files:
#             logger.warning(f"No template YAML files found in {uncompiled_path}")
#
#         files_to_process = []
#         skipped_count = 0
#
#         for template_path in template_files:
#             # Check if this specific file (or its dependencies) changed
#             if force or detector.has_file_changed(template_path):
#                 relative_path = template_path.relative_to(uncompiled_path)
#                 output_file = output_path / relative_path
#                 files_to_process.append((template_path, output_file, {}, "template file"))
#             else:
#                 skipped_count += 1
#                 logger.debug(f"Skipping unchanged file: {template_path}")
#
#         if skipped_count > 0:
#             logger.info(f"Skipped {skipped_count} unchanged file(s)")
#
#         if not files_to_process:
#             logger.info("No files need compilation")
#             return 0
#
#     # Process the files that need compilation
#     # ... existing processing logic ...
#
#     # Mark successfully processed files as compiled
#     if not dry_run:
#         for src_path, _, _, _ in files_to_process:
#             try:
#                 detector._write_hash(
#                     detector._get_hash_file_path(src_path),
#                     detector.compute_content_hash(src_path)
#                 )
#             except Exception as e:
#                 logger.warning(f"Failed to update hash for {src_path}: {e}")
#
#     return total_inlined_count
#
#
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
