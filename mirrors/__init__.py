#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
镜像源处理器包
支持 Docker、APT、YUM、PyPI、npm、Go、Maven、Gradle 等镜像源代理
"""

from .docker import DockerMirror
from .apt import APTMirror
from .yum import YUMMirror
from .pypi import PyPIMirror
from .npm import NpmMirror
from .go import GoProxy
from .http import HttpMirror

# 镜像处理器映射
# 特殊类型使用专用处理器，其他使用通用HTTP处理器
MIRROR_HANDLERS = {
    # 专用处理器
    'docker': DockerMirror,
    'apt': APTMirror,
    'yum': YUMMirror,
    'pypi': PyPIMirror,
    'npm': NpmMirror,
    'go': GoProxy,

    # ======== 包管理器 ========
    # Python
    'pip': HttpMirror,
    'pipenv': HttpMirror,
    'poetry': HttpMirror,
    'conda': HttpMirror,
    'anaconda': HttpMirror,
    'bandersnatch': HttpMirror,
    'twine': HttpMirror,

    # Node.js
    'yarn': HttpMirror,
    'pnpm': HttpMirror,
    'bower': HttpMirror,

    # Java
    'maven': HttpMirror,
    'gradle': HttpMirror,

    # .NET
    'nuget': HttpMirror,

    # Ruby
    'gem': HttpMirror,
    'rubygems': HttpMirror,

    # Rust
    'cargo': HttpMirror,
    'rustup': HttpMirror,

    # PHP
    'composer': HttpMirror,
    'packagist': HttpMirror,

    # Swift/Apple
    'cocoapods': HttpMirror,

    # C/C++
    'conan': HttpMirror,
    'vcpkg': HttpMirror,

    # Dart/Flutter
    'pub': HttpMirror,
    'dart': HttpMirror,
    'flutter': HttpMirror,

    # Haskell
    'hackage': HttpMirror,
    'stackage': HttpMirror,

    # OCaml
    'opam': HttpMirror,

    # D语言
    'dub': HttpMirror,

    # Nim
    'nimble': HttpMirror,

    # V语言
    'v': HttpMirror,

    # Julia
    'julia': HttpMirror,

    # Lua
    'lua': HttpMirror,
    'luarocks': HttpMirror,

    # Elm
    'elm': HttpMirror,

    # Perl
    'cpan': HttpMirror,
    'cpanm': HttpMirror,

    # R
    'cran': HttpMirror,

    # LaTeX
    'ctan': HttpMirror,

    # Haskell
    'haskell': HttpMirror,

    # ======== 容器/云原生 ========
    'helm': HttpMirror,
    'kubernetes': HttpMirror,
    ' Quay.io': HttpMirror,
    'quay': HttpMirror,
    'ghcr': HttpMirror,
    'gcr': HttpMirror,
    'harbor': HttpMirror,

    # ======== 开发工具 ========
    'jetbrains': HttpMirror,
    'vscode': HttpMirror,
    'cuda': HttpMirror,

    # ======== 语言运行时 ========
    'node': HttpMirror,
    'python': HttpMirror,
    'ruby': HttpMirror,
    'php': HttpMirror,
    'java': HttpMirror,
    'dotnet': HttpMirror,

    # ======== Linux 发行版 ========
    'alpine': HttpMirror,
    'arch': HttpMirror,
    'aur': HttpMirror,
    'centos': HttpMirror,
    'debian': HttpMirror,
    'fedora': HttpMirror,
    'gentoo': HttpMirror,
    'opensuse': HttpMirror,
    'void': HttpMirror,
    'freebsd': HttpMirror,
    'netbsd': HttpMirror,
    'openbsd': HttpMirror,
    'rocky': HttpMirror,
    'alma': HttpMirror,
    'kali': HttpMirror,
    'ubuntu': HttpMirror,
    'mint': HttpMirror,
    'manjaro': HttpMirror,
    'slackware': HttpMirror,
    'mageia': HttpMirror,
    'openmandriva': HttpMirror,

    # ======== 系统包管理器 ========
    'homebrew': HttpMirror,
    'brew': HttpMirror,
    'chocolatey': HttpMirror,
    'snap': HttpMirror,
    'flatpak': HttpMirror,
    'appimage': HttpMirror,
    'winget': HttpMirror,
    'scoop': HttpMirror,

    # ======== 数据库/运维 ========
    'postgresql': HttpMirror,
    'mysql': HttpMirror,
    'mariadb': HttpMirror,
    'mongodb': HttpMirror,
    'redis': HttpMirror,
    'influxdata': HttpMirror,
    'grafana': HttpMirror,
    'prometheus': HttpMirror,
    'elastic': HttpMirror,
    'bitnami': HttpMirror,

    # ======== 代码托管/源码 ========
    'git': HttpMirror,
    'github': HttpMirror,
    'gitlab': HttpMirror,
    'bitbucket': HttpMirror,
    'sourceforge': HttpMirror,

    # ======== 其他 ========
    'pacman': HttpMirror,
    'nix': HttpMirror,
    'guix': HttpMirror,
    'termux': HttpMirror,
    'msys2': HttpMirror,
    'google-fonts': HttpMirror,
    'aurora': HttpMirror,
    'cloudflare': HttpMirror,
    'fastly': HttpMirror,

    # ======== 自定义 ========
    'http': HttpMirror,
    'custom': HttpMirror,
}


def get_mirror_handler(mirror_type: str):
    """获取镜像处理器类"""
    return MIRROR_HANDLERS.get(mirror_type)


# 各镜像类型的默认上游URL
DEFAULT_UPSTREAM_URLS = {
    # ======== 包管理器 ========
    # Python
    'pip': 'https://pypi.org/simple',
    'pipenv': 'https://pypi.org/simple',
    'poetry': 'https://pypi.org/simple',
    'conda': 'https://repo.anaconda.com',
    'anaconda': 'https://repo.anaconda.com',
    'bandersnatch': 'https://pypi.org/simple',
    'twine': 'https://pypi.org/simple',

    # Node.js
    'yarn': 'https://registry.yarnpkg.com',
    'pnpm': 'https://registry.npmjs.org',
    'bower': 'https://registry.bower.io',

    # Java
    'maven': 'https://repo1.maven.org/maven2',
    'gradle': 'https://services.gradle.org/distributions',

    # .NET
    'nuget': 'https://api.nuget.org/v3',

    # Ruby
    'gem': 'https://rubygems.org',
    'rubygems': 'https://rubygems.org',

    # Rust
    'cargo': 'https://crates.io',
    'rustup': 'https://static.rust-lang.org',

    # PHP
    'composer': 'https://repo.packagist.org',
    'packagist': 'https://repo.packagist.org',

    # Swift/Apple
    'cocoapods': 'https://cdn.cocoapods.org',

    # C/C++
    'conan': 'https://center.conan.io',
    'vcpkg': 'https://github.com/microsoft/vcpkg/archive/refs/heads/main.tar.gz',

    # Dart/Flutter
    'pub': 'https://pub.dev',
    'dart': 'https://storage.googleapis.com/flutter_infra_release',
    'flutter': 'https://storage.flutter-io.cn',

    # Haskell
    'hackage': 'https://hackage.haskell.org',
    'stackage': 'https://www.stackage.org',

    # OCaml
    'opam': 'https://opam.ocaml.org',

    # D语言
    'dub': 'https://code.dlang.org',

    # Nim
    'nimble': 'https://nimble.directory',

    # V语言
    'v': 'https://vpm.itsgriffin.com',

    # Julia
    'julia': 'https://pkg.julialang.org',

    # Lua
    'lua': 'https://luarocks.org',
    'luarocks': 'https://luarocks.org',

    # Elm
    'elm': 'https://package.elm-lang.org',

    # Perl
    'cpan': 'https://www.cpan.org',
    'cpanm': 'https://www.cpan.org',

    # R
    'cran': 'https://cran.r-project.org',

    # LaTeX
    'ctan': 'https://ctan.math.illinois.edu',

    # Haskell
    'haskell': 'https://haskell.org',

    # ======== 容器/云原生 ========
    'helm': 'https://charts.helm.sh',
    'kubernetes': 'https://dl.k8s.io/release',
    'quay': 'https://quay.io',
    'quay.io': 'https://quay.io',
    'ghcr': 'https://ghcr.io',
    'gcr': 'https://gcr.io',
    'harbor': 'https://harbor.io',

    # ======== 开发工具 ========
    'jetbrains': 'https://www.jetbrains.com',
    'vscode': 'https://code.visualstudio.com',
    'cuda': 'https://developer.download.nvidia.com/compute/cuda/repos',

    # ======== 语言运行时 ========
    'node': 'https://nodejs.org/dist',
    'python': 'https://www.python.org/ftp/python',
    'ruby': 'https://www.ruby-lang.org',
    'php': 'https://www.php.net/distributions',
    'java': 'https://download.oracle.com/java',
    'dotnet': 'https://dotnetcli.azureedge.net',

    # ======== Linux 发行版 ========
    'alpine': 'https://dl-cdn.alpinelinux.org',
    'arch': 'https://mirror.archlinux.org',
    'aur': 'https://aur.archlinux.org',
    'centos': 'https://mirrors.aliyun.com/centos',
    'debian': 'https://deb.debian.org/debian',
    'fedora': 'https://mirrors.fedoraproject.org',
    'gentoo': 'https://distfiles.gentoo.org',
    'opensuse': 'https://download.opensuse.org',
    'void': 'https://repo.voidlinux.org',
    'freebsd': 'https://pkg.freebsd.org',
    'netbsd': 'https://cdn.netbsd.org',
    'openbsd': 'https://cdn.openbsd.org',
    'rocky': 'https://download.rockylinux.org',
    'alma': 'https://repo.almalinux.org',
    'kali': 'http://.kali.org',
    'ubuntu': 'https://releases.ubuntu.com',
    'mint': 'https://packages.linuxmint.com',
    'manjaro': 'https://repo.manjaro.org',
    'slackware': 'https://mirrors.slackware.com',
    'mageia': 'https://www.mageia.org',
    'openmandriva': 'https://download.openmandriva.org',

    # ======== 系统包管理器 ========
    'homebrew': 'https://github.com/Homebrew/brew',
    'brew': 'https://github.com/Homebrew/brew',
    'chocolatey': 'https://chocolatey.org/api/v2',
    'snap': 'https://snapcraft.io',
    'flatpak': 'https://flathub.org',
    'appimage': 'https://github.com/AppImage/AppImageHub/releases',
    'winget': 'https://github.com/microsoft/winget-pkgs',
    'scoop': 'https://scoop.sh',

    # ======== 数据库/运维 ========
    'postgresql': 'https://www.postgresql.org',
    'mysql': 'https://dev.mysql.com',
    'mariadb': 'https://mariadb.org',
    'mongodb': 'https://www.mongodb.org',
    'redis': 'https://redis.io',
    'influxdata': 'https://portal.influxdata.com',
    'grafana': 'https://grafana.com',
    'prometheus': 'https://prometheus.io',
    'elastic': 'https://www.elastic.co',
    'bitnami': 'https://bitnami.com',

    # ======== 代码托管/源码 ========
    'git': 'https://github.com',
    'github': 'https://github.com',
    'gitlab': 'https://gitlab.com',
    'bitbucket': 'https://bitbucket.org',
    'sourceforge': 'https://sourceforge.net',

    # ======== 其他 ========
    'pacman': 'https://mirror.archlinux.org',
    'nix': 'https://nix-community.org',
    'guix': 'https://guix.gnu.org',
    'termux': 'https://termux.net',
    'msys2': 'https://repo.msys2.org',
    'google-fonts': 'https://fonts.google.com',
    'aurora': 'https://auroralinux.org',
    'cloudflare': 'https://cloudflare.com',
    'fastly': 'https://fastly.com',
}


def get_default_upstream(mirror_type: str) -> str:
    """获取镜像类型的默认上游URL"""
    return DEFAULT_UPSTREAM_URLS.get(mirror_type, 'https://mirror.example.com')


def list_available_mirrors() -> list:
    """列出可用的镜像类型"""
    return [
        # ======== 专用处理器 ========
        {
            'type': 'docker',
            'name': 'Docker Registry',
            'description': 'Docker镜像代理'
        },
        {
            'type': 'apt',
            'name': 'APT (Debian/Ubuntu)',
            'description': 'APT软件源代理'
        },
        {
            'type': 'yum',
            'name': 'YUM/DNF (RHEL/CentOS)',
            'description': 'YUM/DNF软件源代理'
        },
        {
            'type': 'pypi',
            'name': 'PyPI',
            'description': 'Python包索引代理'
        },
        {
            'type': 'npm',
            'name': 'npm Registry',
            'description': 'Node.js包管理器代理'
        },
        {
            'type': 'go',
            'name': 'Go Modules',
            'description': 'Go模块代理'
        },

        # ======== 包管理器 ========
        # Python
        {'type': 'pip', 'name': 'pip', 'description': 'Python pip包管理器'},
        {'type': 'pipenv', 'name': 'Pipenv', 'description': 'Python Pipenv代理'},
        {'type': 'poetry', 'name': 'Poetry', 'description': 'Python Poetry包管理器'},
        {'type': 'conda', 'name': 'Conda', 'description': 'Python Conda包管理器'},
        {'type': 'anaconda', 'name': 'Anaconda', 'description': 'Anaconda Python发行版'},

        # Node.js
        {'type': 'yarn', 'name': 'Yarn', 'description': 'Node.js Yarn包管理器'},
        {'type': 'pnpm', 'name': 'pnpm', 'description': 'Node.js pnpm包管理器'},
        {'type': 'bower', 'name': 'Bower', 'description': '前端包管理器'},

        # Java
        {'type': 'maven', 'name': 'Maven Central', 'description': 'Java/Maven包管理器'},
        {'type': 'gradle', 'name': 'Gradle', 'description': 'Gradle构建工具分发'},

        # .NET
        {'type': 'nuget', 'name': 'NuGet', 'description': '.NET包管理器'},

        # Ruby
        {'type': 'gem', 'name': 'RubyGems', 'description': 'Ruby包管理器'},
        {'type': 'rubygems', 'name': 'RubyGems', 'description': 'Ruby官方仓库'},

        # Rust
        {'type': 'cargo', 'name': 'Crates.io', 'description': 'Rust语言包管理器'},
        {'type': 'rustup', 'name': 'Rustup', 'description': 'Rust工具链'},

        # PHP
        {'type': 'composer', 'name': 'Composer', 'description': 'PHP包管理器'},
        {'type': 'packagist', 'name': 'Packagist', 'description': 'PHP官方包仓库'},

        # Swift/Apple
        {'type': 'cocoapods', 'name': 'CocoaPods', 'description': 'iOS/macOS包管理器'},

        # C/C++
        {'type': 'conan', 'name': 'Conan', 'description': 'C/C++包管理器'},
        {'type': 'vcpkg', 'name': 'vcpkg', 'description': 'C/C++包管理器'},

        # Dart/Flutter
        {'type': 'pub', 'name': 'Pub.dev', 'description': 'Dart/Flutter包管理器'},
        {'type': 'dart', 'name': 'Dart SDK', 'description': 'Dart SDK'},
        {'type': 'flutter', 'name': 'Flutter', 'description': 'Flutter SDK'},

        # Haskell
        {'type': 'hackage', 'name': 'Hackage', 'description': 'Haskell包管理器'},
        {'type': 'stackage', 'name': 'Stackage', 'description': 'Haskell Stackage'},

        # OCaml
        {'type': 'opam', 'name': 'OPAM', 'description': 'OCaml包管理器'},

        # D语言
        {'type': 'dub', 'name': 'Dub', 'description': 'D语言包管理器'},

        # Nim
        {'type': 'nimble', 'name': 'Nimble', 'description': 'Nim语言包管理器'},

        # V语言
        {'type': 'v', 'name': 'V PM', 'description': 'V语言包管理器'},

        # Julia
        {'type': 'julia', 'name': 'Julia Packages', 'description': 'Julia语言包管理器'},

        # Lua
        {'type': 'lua', 'name': 'Lua', 'description': 'Lua语言'},
        {'type': 'luarocks', 'name': 'LuaRocks', 'description': 'Lua包管理器'},

        # Elm
        {'type': 'elm', 'name': 'Elm Packages', 'description': 'Elm语言包管理器'},

        # Perl
        {'type': 'cpan', 'name': 'CPAN', 'description': 'Perl包管理器'},
        {'type': 'cpanm', 'name': 'cpanm', 'description': 'Perl cpanminus'},

        # R
        {'type': 'cran', 'name': 'CRAN', 'description': 'R语言包仓库'},

        # LaTeX
        {'type': 'ctan', 'name': 'CTAN', 'description': 'LaTeX包管理器'},

        # ======== 容器/云原生 ========
        {'type': 'helm', 'name': 'Helm Charts', 'description': 'Kubernetes Helm包'},
        {'type': 'kubernetes', 'name': 'Kubernetes', 'description': 'Kubernetes发行版'},
        {'type': 'quay', 'name': 'Quay.io', 'description': 'Quay容器仓库'},
        {'type': 'ghcr', 'name': 'GitHub Container Registry', 'description': 'GitHub容器仓库'},
        {'type': 'gcr', 'name': 'Google Container Registry', 'description': 'Google容器仓库'},
        {'type': 'harbor', 'name': 'Harbor', 'description': 'Harbor容器仓库'},

        # ======== 开发工具 ========
        {'type': 'jetbrains', 'name': 'JetBrains', 'description': 'JetBrains IDE'},
        {'type': 'vscode', 'name': 'VS Code', 'description': 'Visual Studio Code'},
        {'type': 'cuda', 'name': 'CUDA', 'description': 'NVIDIA CUDA工具包'},

        # ======== 语言运行时 ========
        {'type': 'node', 'name': 'Node.js', 'description': 'Node.js官方'},
        {'type': 'python', 'name': 'Python', 'description': 'Python官方'},
        {'type': 'ruby', 'name': 'Ruby', 'description': 'Ruby官方'},
        {'type': 'php', 'name': 'PHP', 'description': 'PHP官方'},
        {'type': 'java', 'name': 'Java JDK', 'description': 'Oracle/OpenJDK'},
        {'type': 'dotnet', 'name': '.NET SDK', 'description': '.NET SDK'},

        # ======== Linux 发行版 ========
        {'type': 'alpine', 'name': 'Alpine Linux', 'description': 'Alpine Linux'},
        {'type': 'arch', 'name': 'Arch Linux', 'description': 'Arch Linux'},
        {'type': 'aur', 'name': 'AUR', 'description': 'Arch Linux AUR'},
        {'type': 'centos', 'name': 'CentOS', 'description': 'CentOS'},
        {'type': 'debian', 'name': 'Debian', 'description': 'Debian'},
        {'type': 'fedora', 'name': 'Fedora', 'description': 'Fedora'},
        {'type': 'gentoo', 'name': 'Gentoo', 'description': 'Gentoo'},
        {'type': 'opensuse', 'name': 'openSUSE', 'description': 'openSUSE'},
        {'type': 'void', 'name': 'Void Linux', 'description': 'Void Linux'},
        {'type': 'freebsd', 'name': 'FreeBSD', 'description': 'FreeBSD'},
        {'type': 'netbsd', 'name': 'NetBSD', 'description': 'NetBSD'},
        {'type': 'openbsd', 'name': 'OpenBSD', 'description': 'OpenBSD'},
        {'type': 'rocky', 'name': 'Rocky Linux', 'description': 'Rocky Linux'},
        {'type': 'alma', 'name': 'AlmaLinux', 'description': 'AlmaLinux'},
        {'type': 'kali', 'name': 'Kali Linux', 'description': 'Kali Linux'},
        {'type': 'ubuntu', 'name': 'Ubuntu', 'description': 'Ubuntu'},
        {'type': 'mint', 'name': 'Linux Mint', 'description': 'Linux Mint'},
        {'type': 'manjaro', 'name': 'Manjaro', 'description': 'Manjaro Linux'},
        {'type': 'slackware', 'name': 'Slackware', 'description': 'Slackware'},
        {'type': 'mageia', 'name': 'Mageia', 'description': 'Mageia Linux'},
        {'type': 'openmandriva', 'name': 'OpenMandriva', 'description': 'OpenMandriva'},

        # ======== 系统包管理器 ========
        {'type': 'homebrew', 'name': 'Homebrew', 'description': 'macOS Homebrew'},
        {'type': 'brew', 'name': 'Brew', 'description': 'Homebrew'},
        {'type': 'chocolatey', 'name': 'Chocolatey', 'description': 'Windows Chocolatey'},
        {'type': 'snap', 'name': 'Snap Store', 'description': 'Snap应用商店'},
        {'type': 'flatpak', 'name': 'Flatpak', 'description': 'Flatpak应用'},
        {'type': 'appimage', 'name': 'AppImage', 'description': 'AppImage应用'},
        {'type': 'winget', 'name': 'winget', 'description': 'Windows winget'},
        {'type': 'scoop', 'name': 'Scoop', 'description': 'Windows Scoop'},

        # ======== 数据库/运维 ========
        {'type': 'postgresql', 'name': 'PostgreSQL', 'description': 'PostgreSQL数据库'},
        {'type': 'mysql', 'name': 'MySQL', 'description': 'MySQL数据库'},
        {'type': 'mariadb', 'name': 'MariaDB', 'description': 'MariaDB数据库'},
        {'type': 'mongodb', 'name': 'MongoDB', 'description': 'MongoDB数据库'},
        {'type': 'redis', 'name': 'Redis', 'description': 'Redis数据库'},
        {'type': 'influxdata', 'name': 'InfluxData', 'description': 'InfluxDB时序数据库'},
        {'type': 'grafana', 'name': 'Grafana', 'description': 'Grafana可视化'},
        {'type': 'prometheus', 'name': 'Prometheus', 'description': 'Prometheus监控'},
        {'type': 'elastic', 'name': 'Elastic', 'description': 'Elasticsearch'},

        # ======== 代码托管 ========
        {'type': 'github', 'name': 'GitHub', 'description': 'GitHub代码托管'},
        {'type': 'gitlab', 'name': 'GitLab', 'description': 'GitLab代码托管'},
        {'type': 'bitbucket', 'name': 'Bitbucket', 'description': 'Bitbucket代码托管'},
        {'type': 'sourceforge', 'name': 'SourceForge', 'description': 'SourceForge开源托管'},

        # ======== 其他 ========
        {'type': 'nix', 'name': 'Nix/NixOS', 'description': 'Nix包管理器'},
        {'type': 'guix', 'name': 'Guix', 'description': 'Guix包管理器'},
        {'type': 'termux', 'name': 'Termux', 'description': 'Termux包管理器'},
        {'type': 'msys2', 'name': 'MSYS2', 'description': 'MSYS2包管理器'},
        {'type': 'google-fonts', 'name': 'Google Fonts', 'description': 'Google字体库'},

        # ======== 自定义 ========
        {'type': 'custom', 'name': '自定义HTTP', 'description': '自定义HTTP镜像源'}
    ]
