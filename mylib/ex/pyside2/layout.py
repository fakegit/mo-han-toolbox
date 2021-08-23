#!/usr/bin/env python3
from PySide2.QtCore import *
from PySide2.QtWidgets import *

from mylib.easy import T


class EzQtLayoutWrapper:
    def __init__(self, layout_class, owner_widget=None, parent=None):
        self.widget = owner_widget or QWidget(parent)
        self.layout = layout_class(self.widget)
        self.widget.setLayout(self.layout)

    @staticmethod
    def __get_widget_from__(x):
        if isinstance(x, QWidget):
            return x
        elif hasattr(x, 'widget') and isinstance(x.widget, QWidget):
            return x.widget
        else:
            raise ValueError('get no widget from this object')

    def add(self, *widgets):
        layout = self.layout
        for x in widgets:
            if isinstance(x, dict):
                for k, v in x.items():
                    m = getattr(layout, f'add{k.title()}')
                    if isinstance(v, T.Iterable):
                        m(*v)
                    else:
                        m(v)
            elif isinstance(x, T.Iterable):
                args = list(x)
                first, *others = args
                w = self.__get_widget_from__(first)
                layout.addWidget(w, *others)
            else:
                layout.addWidget(self.__get_widget_from__(x))
        return self


class EzQtScrollArea(EzQtLayoutWrapper):
    def __init__(self, layout_class, parent=None, resizable=True):
        self.area = QScrollArea(parent)
        widget = QWidget(self.area)
        self.area.setWidget(widget)
        self.area.setWidgetResizable(resizable)
        super().__init__(layout_class, widget, parent=parent)


class EzQtHFlow(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(QMargins(0, 0, 0, 0))
        self._item_list = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._re_calc_height_from_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(EzQtHFlow, self).setGeometry(rect)
        self._re_calc_height_from_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def _re_calc_height_from_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._item_list:
            style = item.widget().style()
            layout_spacing_x = style.layoutSpacing(QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal)
            layout_spacing_y = style.layoutSpacing(QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Vertical)
            space_x = spacing + layout_spacing_x
            space_y = spacing + layout_spacing_y
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()
