from inotify_simple import INotify, flags   # type: ignore
from typing import Optional, Dict, Set
from pathlib import Path

from dockerdo.config import Session, MountSpecs
from dockerdo import prettyprint

IGNORE_PATHS = {Path(x) for x in ("/proc", "/dev", "/sys", "/var")}


class InotifyListener:
    def __init__(self, session: Session, verbose: bool = False) -> None:
        self.session = session
        self.inotify: Optional[INotify] = None
        self.watch_flags = flags.CLOSE_WRITE | flags.UNMOUNT
        self.watch_descriptors: Dict[int, Path] = {}
        self.session_watch_descriptor: Optional[int] = None
        self.seen_mounts: Set[MountSpecs] = set()
        self.verbose = verbose

    def register_all_listeners(self) -> None:
        """
        Register listeners recursively for the session's container mount point.
        """
        self.inotify = INotify()
        try:
            self.session_watch_descriptor = self.inotify.add_watch(
                self.session.session_dir / "session.yaml", mask=self.watch_flags
            )
        except PermissionError:
            pass
        except OSError:
            pass
        for mount_specs in self.session.mounts:
            self.seen_mounts.add(mount_specs)
            if mount_specs.near_host == "local":
                if self.verbose:
                    prettyprint.info(f"Registering listeners for {mount_specs.descr_str()}")
                self.register_listeners(mount_specs.near_path, mount_specs.far_path)

    def register_listeners(self, near_path: Path, far_path: Path) -> None:
        assert self.inotify is not None
        # Add watch for the current directory
        try:
            wd = self.inotify.add_watch(near_path, mask=self.watch_flags)
            self.watch_descriptors[wd] = far_path
        except PermissionError:
            pass
        except OSError:
            pass

        # Recurse into subdirectories
        for path in near_path.glob("*"):
            path_inside_container = far_path / path.name
            if any(path_inside_container.is_relative_to(x) for x in IGNORE_PATHS):
                continue
            if path.is_dir():
                self.register_listeners(path, path_inside_container)

    def register_listeners_for_new_mounts(self) -> None:
        for mount_specs in self.session.mounts:
            if mount_specs.near_host == "local" and mount_specs not in self.seen_mounts:
                self.seen_mounts.add(mount_specs)
                if self.verbose:
                    prettyprint.info(f"Registering listeners for new mount {mount_specs.descr_str()}")
                self.register_listeners(mount_specs.near_path, mount_specs.far_path)

    def listen(self) -> None:
        if self.inotify is None:
            raise RuntimeError("Listeners not registered")
        while self.session.container_state == "running":
            for event in self.inotify.read(timeout=5000):
                try:
                    wd, mask, cookie, name = event
                    if mask & flags.UNMOUNT:
                        # Backing filesystem unmounted
                        if self.verbose:
                            prettyprint.info('Backing filesystem unmounted')
                        return
                    if wd == self.session_watch_descriptor:
                        # Reload the session to update the container state
                        self.session = Session.load(self.session.session_dir)
                        self.register_listeners_for_new_mounts()
                        continue
                    if ".mutagen-temporary-cross-device-rename" in name:
                        # Ignore mutagen temporary files
                        continue
                    path = self.watch_descriptors[wd] / name
                    if not self.session.record_modified_file(path):
                        continue
                    if self.verbose:
                        prettyprint.info(f"Recorded modified file: {path}")
                except KeyError:
                    pass
