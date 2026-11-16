TARGET = harbour-bookfish

CONFIG += sailfishapp_qml sailfishapp_i18n

# Only the module files, so local __pycache__ or tests never end up in the package.
python.files = python/bookfish/*.py
python.path = /usr/share/$${TARGET}/python/bookfish

SAILFISHAPP_ICONS = 86x86 108x108 128x128 172x172

# The guide, a readaloud opened on the first start (see guide/README.md).
guide.files = guide/welcome-to-bookfish.epub
guide.path = /usr/share/$${TARGET}/guide

INSTALLS += python guide

DISTFILES += \
    qml/harbour-bookfish.qml \
    qml/pages/*.qml \
    qml/cover/*.qml \
    qml/components/*.qml \
    qml/js/*.js \
    python/bookfish/*.py \
    rpm/harbour-bookfish.spec \
    harbour-bookfish.desktop
