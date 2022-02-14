import json
from dataclasses import dataclass, field
from datetime import datetime
from logging import getLogger
from typing import Any, Dict, List, Optional

from dataclasses_json import DataClassJsonMixin, LetterCase, config
from marshmallow import fields

from .common import get_json


log = getLogger(__name__)


@dataclass
class Download(DataClassJsonMixin):
    sha1: str
    size: int
    url: str


@dataclass
class Version(DataClassJsonMixin):
    id: str
    type: str
    url: str
    time: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format="iso"),
        )
    )
    release_time: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format="iso"),
            letter_case=LetterCase.CAMEL,  # type: ignore
        )
    )

    def get_manifest(self) -> Any:
        """Return the version's manifest."""
        return get_json(self.url)

    def get_downloads(self) -> Dict[str, Download]:
        """
        Return all downloadable files from the version's manifest, in Download
        objects.
        """
        return {
            download_name: Download.from_dict(download_info)
            for download_name, download_info in self.get_manifest()["downloads"].items()
        }

    def get_java_version(self) -> Any:
        """
        Return the java version specified in a version's manifest, if it is
        present. Versions <= 1.6 do not specify this.
        """
        return self.get_manifest().get("javaVersion", {}).get("majorVersion", None)

    def get_server(self) -> Optional[Download]:
        """
        If the version has a server download available, return the Download
        object for the server download. If the version does not have a server
        download avilable, return None.
        """
        downloads = self.get_downloads()
        if "server" in downloads:
            return downloads["server"]
        return None


def get_versions() -> List[Version]:
    """Return a list of Version objects for all available versions."""
    return [
        Version.from_dict(version)
        for version in get_json(
            "https://launchermeta.mojang.com/mc/game/version_manifest/sources.json"
        )["versions"]
    ]


def get_major_release(version_id: str) -> str:
    """
    Return the major release for a version. The major release for 1.17 and
    1.17.1 is 1.17.
    """
    if not len(version_id.split(".")) >= 2:
        raise ValueError(f"version not in expected format: '{version_id}'")
    return ".".join(version_id.split(".")[:2])


def group_major_releases(releases: List[Version]) -> Dict[str, List[Version]]:
    """
    Return a dictionary containing each version grouped by each major release.
    The key "1.17" contains a list with two Version objects, one for "1.17"
    and another for "1.17.1".
    """
    groups: Dict[str, List[Version]] = {}
    for release in releases:
        major_release = get_major_release(release.id)
        if major_release not in groups:
            groups[major_release] = []
        groups[major_release].append(release)
    return groups


def get_latest_major_releases(releases: List[Version]) -> Dict[str, Version]:
    """
    Return a dictionary containing the latest version for each major release.
    The latest major release for 1.16 is 1.16.5, so the key "1.16" contains a
    Version object for 1.16.5.
    """
    return {
        major_release: sorted(releases, key=lambda x: x.id, reverse=True)[0]
        for major_release, releases in group_major_releases(releases).items()
    }


def generate() -> Dict[str, Dict[str, str]]:
    """
    Return a dictionary containing the latest url, sha1 and version for each major
    release.
    """
    versions = get_versions()
    releases = list(
        filter(lambda version: version.type == "release", versions)
    )  # remove snapshots and betas
    latest_major_releases = get_latest_major_releases(releases)

    servers = {
        version: Download.schema().dump(download_info)  # Download -> dict
        for version, download_info in {
            version: value.get_server()
            for version, value in latest_major_releases.items()
        }.items()
        if download_info is not None  # versions < 1.2 do not have a server
    }
    for server in servers.values():
        del server["size"]  # don't need it

    for version, server in servers.items():
        server["version"] = latest_major_releases[version].id
        server["javaVersion"] = latest_major_releases[version].get_java_version()
    return servers


def main() -> None:
    with open("packages/vanilla/sources.json", "w") as file:
        data = generate()
        log.info(f"[b]Found {len(data.keys())} versions for Vanilla")
        json.dump(data, file, indent=2)
        file.write("\n")


if __name__ == "__main__":
    main()