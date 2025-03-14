# Code style

- This project uses `mypy` for type checking: add type annotations to all function arguments and return values.
- Write testable code. If it is possible to extract logic into a pure function, prefer refactoring to use the pure function instead of mixing logic with side effects.

# Libraries

## click

Use `click` to create the command line interface.
Use the `@click.group()` decorator to create subcommands.

## rich

Use `rich` to produce good-looking output with color and formatting.

## subprocess

Use `subprocess` to run commands, mainly `ssh` and `sshfs`.
Make sure that stdin, stdout, and stderr are piped through correctly: io should be realtime (not buffering everything until the end of the command), and large writes should not be truncated due to buffering.

## inotify-simple

Use `inotify-simple` to listen to filesystem writes in the sshfs-mounted subdirectories.
Listen recursively in all the subdirectories of the mount point.

## pydantic

Use `pydantic` version 2 to represent and serialize data, and to validate the config.



# File locations

- Store the user config in `.config/dockerdo/dockerdorc`.
- Store the session data in either of two locations, depending on the context.
    - If the user names the session, it is a persistent session stored in `./local/share/dockerdo`.
    - If the user does not name the session, it is an ephemeral session stored in a temporary directory created with `mkdtemp`.
- Mount the sshfs filesystems under two subdirectories of the working directory.
    - Create the subdirectories if they don't exist yet, but stop with an error if they exist and are not empty.
    - The remote host is mounted in a subdirectory matching the name of the remote machine.
    - The container is mounted in a subdirectory matching the name of the persistent session, or `container` for ephemeral sessions.


# Using ssh

- Use `ssh` with the `-J` option to jump via the remote host to the container.
- Use `ssh -M -S ${SESSION_DIR}/ssh-socket` to create a master connection that can be used for multiple commands.
  The following commands should use `ssh -S ${SESSION_DIR}/ssh-socket` to reuse the master connection.
