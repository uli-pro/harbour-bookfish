Name:       harbour-bookfish
Summary:    Read e-books and listen to audiobooks and readalouds
Version:    0.1.0
Release:    1
License:    GPL-3.0-or-later
BuildArch:  noarch
URL:        https://github.com/uli-pro/harbour-bookfish
Source0:    %{name}-%{version}.tar.bz2
Requires:   sailfishsilica-qt5 >= 0.10.9
Requires:   libsailfishapp-launcher
Requires:   pyotherside-qml-plugin-python3-qt5 >= 1.5
Requires:   sailfish-components-webview-qt5
Requires:   qt5-qtdeclarative-import-multimedia
Requires:   amber-qml-plugin-mpris
Requires:   python3-sqlite
BuildRequires:  pkgconfig(sailfishapp) >= 1.0.3
BuildRequires:  pkgconfig(Qt5Core)
BuildRequires:  pkgconfig(Qt5Qml)
BuildRequires:  pkgconfig(Qt5Quick)
BuildRequires:  qt5-qttools-linguist
BuildRequires:  desktop-file-utils

%description
Read e-books and listen to audiobooks and readalouds. Readalouds are
EPUB 3 books with synchronized narration (Media Overlays), so you can
continue listening at the sentence where you stopped reading.

%prep
%setup -q -n %{name}-%{version}

%build
%qmake5
%make_build

%install
%qmake5_install
desktop-file-install --delete-original \
    --dir %{buildroot}%{_datadir}/applications \
    %{buildroot}%{_datadir}/applications/*.desktop

%files
%defattr(-,root,root,-)
%{_datadir}/%{name}
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/*/apps/%{name}.png
