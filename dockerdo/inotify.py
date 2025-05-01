from inotify_simple import INotify, flags   # type: ignore
from typing import Optional, Dict
from pathlib import Path

from dockerdo.config import Session
from dockerdo import prettyprint

IGNORE_PATHS = {Path(x) for x in ("/proc", "/dev", "/sys")}


class InotifyListener:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.inotify: Optional[INotify] = None
        self.watch_flags = flags.CLOSE_WRITE | flags.UNMOUNT
        self.watch_descriptors: Dict[int, Path] = {}

    def register_listeners(self) -> None:
        """
        Register listeners recursively for the session's container mount point.
        """
        self.inotify = INotify()
        for path in self.session.sshfs_container_mount_point.rglob("*"):
            path_inside_container = Path("/") / path.relative_to(
                self.session.sshfs_container_mount_point
            )
            if any(path_inside_container.is_relative_to(x) for x in IGNORE_PATHS):
                continue
            if path.is_dir():
                try:
                    wd = self.inotify.add_watch(path, mask=self.watch_flags)
                    self.watch_descriptors[wd] = path_inside_container
                except PermissionError:
                    pass
                except OSError:
                    pass

    def listen(self, verbose: bool = False) -> None:
        if self.inotify is None:
            raise RuntimeError("Listeners not registered")
        while self.session.container_state == "running":
            for event in self.inotify.read(timeout=5000):
                try:
                    wd, mask, cookie, name = event
                    if mask & flags.UNMOUNT:
                        # Backing filesystem unmounted
                        if verbose:
                            prettyprint.info('Backing filesystem unmounted')
                        return
                    path = self.watch_descriptors[wd] / name
                    if not self.session.record_modified_file(path):
                        continue
                    if verbose:
                        prettyprint.info(f"Recorded modified file: {path}")
                except KeyError:
                    pass
            # Reload the session to update the container state
            self.session = Session.load(self.session.session_dir)
