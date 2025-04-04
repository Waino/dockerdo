from inotify_simple import INotify, flags   # type: ignore
from typing import Optional, Dict
from pathlib import Path

from dockerdo.config import Session
from dockerdo import prettyprint


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
            if path.is_dir():
                try:
                    wd = self.inotify.add_watch(path, mask=self.watch_flags)
                    path_inside_container = Path("/") / path.relative_to(
                        self.session.sshfs_container_mount_point
                    )
                    self.watch_descriptors[wd] = path_inside_container
                except PermissionError:
                    pass

    def listen(self, verbose: bool = False) -> None:
        if self.inotify is None:
            raise RuntimeError("Listeners not registered")
        while self.session.container_state == "running":
            for event in self.inotify.read(timeout=5000):
                try:
                    self.session = Session.load(self.session.session_dir)
                    wd, mask, cookie, name = event
                    if mask & flags.UNMOUNT:
                        # Backing filesystem unmounted
                        if verbose:
                            prettyprint.info('Backing filesystem unmounted')
                        return
                    path = self.watch_descriptors[wd] / name
                    self.session.record_modified_file(path)
                    self.session.save()
                    if verbose:
                        prettyprint.info(f"Recorded modified file: {path}")
                except KeyError:
                    pass
            self.session = Session.load(self.session.session_dir)
