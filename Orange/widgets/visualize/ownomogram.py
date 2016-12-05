import time
from enum import IntEnum

import numpy as np

from AnyQt.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsSimpleTextItem,
    QGraphicsTextItem, QGraphicsLineItem, QGraphicsWidget, QGraphicsRectItem,
    QGraphicsEllipseItem, QGraphicsLinearLayout, QGridLayout, QLabel, QFrame
)
from AnyQt.QtGui import QColor, QPainter, QFont, QPen
from AnyQt.QtCore import Qt, QEvent, QRectF

from Orange.data import Table, Domain
from Orange.classification import Model
from Orange.classification.naive_bayes import NaiveBayesModel
from Orange.classification.logistic_regression import \
    LogisticRegressionClassifier
from Orange.widgets.settings import Setting, ContextSetting, \
    DomainContextHandler
from Orange.widgets.widget import OWWidget, Msg
from Orange.widgets import gui


class SortBy(IntEnum):
    NO_SORTING, NAME, ABSOLUTE, POSITIVE, NEGATIVE = 0, 1, 2, 3, 4

    @staticmethod
    def items():
        return ["No sorting", "Name", "Absolute importance",
                "Positive influence", "Negative influence"]


class MovableToolTip(QLabel):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setWindowFlags(Qt.ToolTip)
        self.hide()

    def show(self, pos, text, change_y=True):
        self.move(pos.x(), pos.y() + 15 if change_y else self.y())
        self.setText(text)
        self.adjustSize()
        super().show()


class BaseDotItem(QGraphicsEllipseItem):
    TOOLTIP_STYLE = """ul {margin-top: 1px; margin-bottom: 1px;}"""
    TOOLTIP_TEMPLATE = """<html><head><style type="text/css">{}</style>
    </head><body><b>{}</b><hr/>{}</body></html>
    """

    def __init__(self, r, scale, offset, min_x, max_x):
        super().__init__(0, 0, r, r)
        self._r = r
        self._min_x = min_x * scale - r / 2 + offset
        self._max_x = max_x * scale - r / 2 + offset
        self._scale = scale
        self._offset = offset
        self.setPos(0, - r / 2)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setBrush(QColor(70, 190, 250, 255))
        self.setZValue(100)
        self.tool_tip = MovableToolTip()
        self.setAcceptHoverEvents(True)

    @property
    def value(self):
        return (self.x() + self._r / 2 - self._offset) / self._scale

    def move(self, x):
        self.setX(x)

    def move_to_val(self, val):
        x = self._scale * val - self._r / 2 + self._offset
        if x < self._min_x:
            x = self._min_x
        if x > self._max_x:
            x = self._max_x
        self.move(x)

    def hoverEnterEvent(self, event):
        self.tool_tip.show(event.screenPos(), self.get_tooltip_text())

    def hoverLeaveEvent(self, event):
        self.tool_tip.hide()


class DotItem(BaseDotItem):
    def __init__(self, r, scale, offset, min_x, max_x, title=None,
                 get_probabilities=None):
        self.title = title
        self.get_probabilities = get_probabilities
        self.movable_dot_items = []
        super().__init__(r, scale, offset, min_x, max_x)

    def mouseMoveEvent(self, _):
        return

    def move_to_sum(self):
        if not self.movable_dot_items:
            return
        total = sum(item.value for item in self.movable_dot_items)
        self.move_to_val(total)

    def get_tooltip_text(self):
        value = self.value
        if self.get_probabilities is not None:
            value = self.get_probabilities(value)
        return self.TOOLTIP_TEMPLATE.format(
            self.TOOLTIP_STYLE, self.title,
            "Value: {}".format(np.round(value, 2)))


class MovableDotItem(BaseDotItem):
    def __init__(self, r, scale, offset, min_x, max_x):
        self.tooltip_labels = []
        self.tooltip_values = []
        super().__init__(r, scale, offset, min_x, max_x)
        self._x = min_x * scale - r / 2 + offset
        self._point_dot = None
        self._total_dot = None
        self._probs_dot = None
        self._vertical_line = None

    @property
    def vertical_line(self):
        return self._vertical_line

    @vertical_line.setter
    def vertical_line(self, line):
        line.setVisible(False)
        self._vertical_line = line

    @property
    def point_dot(self):
        return self._point_dot

    @point_dot.setter
    def point_dot(self, dot):
        dot.setVisible(False)
        self._point_dot = dot

    @property
    def total_dot(self):
        return self._total_dot

    @total_dot.setter
    def total_dot(self, dot):
        self._total_dot = dot
        self._total_dot.movable_dot_items.append(self)

    @property
    def probs_dot(self):
        return self._probs_dot

    @probs_dot.setter
    def probs_dot(self, dot):
        self._probs_dot = dot
        self._probs_dot.movable_dot_items.append(self)

    def mousePressEvent(self, event):
        self.tool_tip.show(event.screenPos(), self.get_tooltip_text(), False)
        self._x = event.pos().x()
        self.setBrush(QColor(50, 150, 200, 255))
        self._show_vertical_line_and_point_dot()
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.tool_tip.show(event.screenPos(), self.get_tooltip_text(), False)
        delta_x = event.pos().x() - self._x
        if self._min_x <= self.x() + delta_x <= self._max_x:
            self.move(self.x() + delta_x)
            mod_tooltip_values = [0] + list(self.tooltip_values)
            if np.round(self.value, 1) in np.round(mod_tooltip_values, 1):
                index = np.where(np.round(mod_tooltip_values, 1) ==
                                 np.round(self.value, 1))
                time.sleep(0.05)
                self.move_to_val((mod_tooltip_values)[index[0][0]])
        elif self.x() + delta_x < self._min_x:
            self.move(self._min_x)
        elif self.x() + delta_x > self._max_x:
            self.move(self._max_x)
        self._show_vertical_line_and_point_dot()
        self.total_dot.move_to_sum()
        self.probs_dot.move_to_sum()

    def mouseReleaseEvent(self, event):
        self.tool_tip.hide()
        self.setBrush(QColor(70, 190, 250, 255))
        self.point_dot.setVisible(False)
        self.vertical_line.setVisible(False)
        return super().mousePressEvent(event)

    def _show_vertical_line_and_point_dot(self):
        self.vertical_line.setX(self.x() + self._r / 2 - self._offset)
        self.vertical_line.setVisible(True)
        self.point_dot.move_to_val(self.value)
        self.point_dot.setVisible(True)


class DiscreteMovableDotItem(MovableDotItem):
    def get_tooltip_text(self):
        labels = self._get_tooltip_labels_with_percentages()
        return self.TOOLTIP_TEMPLATE.format(
            self.TOOLTIP_STYLE, "Points: {}".format(np.round(self.value, 2)),
            "".join("{}: {:.2%}<br/>".format(l, v) for l, v in labels)[:-5])

    def _get_tooltip_labels_with_percentages(self):
        if not len(self.tooltip_labels):
            return []
        for i, val in enumerate(self.tooltip_values):
            if val > self.value:
                break
        diff = self.tooltip_values[i] - self.tooltip_values[i - 1]
        p1 = 0 if diff < 1e-6 else (-self.value + self.tooltip_values[i]) / diff
        return [(self.tooltip_labels[i - 1].replace("<", "&lt;"), abs(p1)),
                (self.tooltip_labels[i].replace("<", "&lt;"), abs(1 - p1))]


class ContinuousItemMixin:
    def get_tooltip_text(self):
        return self.TOOLTIP_TEMPLATE.format(
            self.TOOLTIP_STYLE, "Points: {}".format(np.round(self.value, 2)),
            "Value: {}".format(np.round(self._get_tooltip_label_value(), 1)))

    def _get_tooltip_label_value(self):
        if not len(self.tooltip_labels):
            return self.value
        start = float(self.tooltip_labels[0])
        stop = float(self.tooltip_labels[-1])
        delta = (self.tooltip_values[-1] - self.tooltip_values[0])
        return start + self.value * (stop - start) / delta


class ContinuousMovableDotItem(MovableDotItem, ContinuousItemMixin):
    pass


class Continuous2DMovableDotItem(MovableDotItem, ContinuousItemMixin):
    def __init__(self, r, scale, offset, min_x, max_x, min_y, max_y):
        super().__init__(r, scale, offset, min_x, max_x)
        self._min_y = min_y
        self._max_y = max_y
        self._horizontal_line = None

    @property
    def horizontal_line(self):
        return self._horizontal_line

    @horizontal_line.setter
    def horizontal_line(self, line):
        line.setVisible(False)
        self._horizontal_line = line

    def move(self, x):
        super().move(x)
        k = (x - self._min_x) / (self._max_x - self._min_x)
        self.setY(self._min_y - self._r / 2 + (self._max_y - self._min_y) * k)

    def mousePressEvent(self, event):
        self._show_horizontal_line()
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._show_horizontal_line()

    def mouseReleaseEvent(self, event):
        self.horizontal_line.setVisible(False)
        return super().mouseReleaseEvent(event)

    def _show_horizontal_line(self):
        self.horizontal_line.setY(self.y() + self._r / 2 -
                                  abs(self._max_y - self._min_y) / 2)
        self.horizontal_line.setVisible(True)


class RulerItem(QGraphicsWidget):
    tick_height = 6
    tick_width = 0
    dot_r = 10
    half_tick_height = 3
    bold_label = True
    DOT_ITEM_CLS = DotItem

    def __init__(self, name, values, scale, name_offset, offset, labels=None,
                 **dot_kwargs):
        super().__init__()

        # leading label
        font = name.document().defaultFont()
        if self.bold_label:
            font.setWeight(QFont.Bold)
        name.setFont(font)
        name.setPos(name_offset, -10)
        name.setParentItem(self)

        # prediction marker
        self.dot = self.DOT_ITEM_CLS(
            self.dot_r, scale, offset, values[0], values[-1], **dot_kwargs)
        self.dot.setParentItem(self)

        # line
        line = QGraphicsLineItem(min(values) * scale + offset, 0,
                                 max(values) * scale + offset, 0)
        line.setParentItem(self)

        old_x_tick = None
        func = len(dot_kwargs) > 1 and dot_kwargs["get_probabilities"]
        if labels is None:
            labels = [str(np.round(func(v), 2)) for v in values] if func \
                else [str(abs(v) if v == -0 else v) for v in values]

        def collides(_item):
            for _it in shown_items:
                if _item.collidesWithItem(_it):
                    return True
            return False

        shown_items = []
        w = QGraphicsSimpleTextItem(labels[0]).boundingRect().width()
        text_finish = values[0] * scale - w + offset - 10
        for i, (label, value) in enumerate(zip(labels, values)):
            text = QGraphicsSimpleTextItem(label)
            x_text = value * scale - text.boundingRect().width() / 2 + offset
            if text_finish > x_text - 10:
                y_text, y_tick = self.dot_r * 0.7, -self.tick_height
                text_finish = values[0] * scale + offset
            else:
                y_text = - text.boundingRect().height() - self.dot_r * 0.7
                y_tick = 0
                text_finish = x_text + text.boundingRect().width()
            text.setPos(x_text, y_text)
            if not collides(text):
                text.setParentItem(self)
                shown_items.append(text)

            x_tick = value * scale - self.tick_width / 2 + offset
            tick = QGraphicsRectItem(
                x_tick, y_tick, self.tick_width, self.tick_height)
            tick.setBrush(QColor(Qt.black))
            tick.setParentItem(self)

            if self.half_tick_height and i and not func:
                x = x_tick - (x_tick - old_x_tick) / 2
                half_tick = QGraphicsLineItem(x, 0, x, self.half_tick_height)
                half_tick.setParentItem(self)
            old_x_tick = x_tick


class DiscreteFeatureItem(RulerItem):
    tick_height = 6
    tick_width = 2
    half_tick_height = 0
    dot_r = 14
    bold_label = False
    DOT_ITEM_CLS = DiscreteMovableDotItem

    def __init__(self, name, labels, values, scale, name_offset, offset, coef):
        self.name = name.toPlainText()
        self.min_value = min(coef)
        self.max_value = max(coef)
        self.diff = self.max_value - self.min_value
        indices = np.argsort(values)
        labels, values = np.array(labels)[indices], values[indices]
        super().__init__(name, values, scale, name_offset, offset, labels)
        self.dot.tooltip_labels = labels
        self.dot.tooltip_values = values


class ContinuousFeatureItem(RulerItem):
    tick_height = 6
    tick_width = 2
    half_tick_height = 0
    dot_r = 14
    bold_label = False
    DOT_ITEM_CLS = ContinuousMovableDotItem

    def __init__(self, name, data_extremes, values, scale, name_offset, offset,
                 coef):
        self.name = name.toPlainText()
        self.diff = (data_extremes[1] - data_extremes[0]) * coef
        k = (data_extremes[1] - data_extremes[0]) / (values[-1] - values[0])
        labels = [str(np.round(v * k + data_extremes[0], 1)) for v in values]
        super().__init__(name, values, scale, name_offset, offset, labels)
        self.dot.tooltip_labels = labels
        self.dot.tooltip_values = values


class ContinuousFeature2DItem(QGraphicsWidget):
    tick_height = 6
    tick_width = 2
    dot_r = 14
    y_diff = 80
    n_tck = 4

    def __init__(self, name, data_extremes, values, scale, name_offset, offset,
                 coef):
        super().__init__()
        data_start, data_stop = data_extremes[0], data_extremes[1]
        self.name = name.toPlainText()
        self.diff = (data_stop - data_start) * coef
        labels = [str(np.round(data_start + (data_stop - data_start) * i /
                               (self.n_tck - 1), 1)) for i in range(self.n_tck)]

        # leading label
        font = name.document().defaultFont()
        name.setFont(font)
        name.setPos(name_offset, -10)
        name.setParentItem(self)

        # labels
        ascending = data_start < data_stop
        y_start, y_stop = (self.y_diff, 0) if ascending else (0, self.y_diff)
        for i in range(self.n_tck):
            text = QGraphicsSimpleTextItem(labels[i])
            w = text.boundingRect().width()
            y = y_start + (y_stop - y_start) / (self.n_tck - 1) * i
            text.setPos(-5 - w, y - 8)
            text.setParentItem(self)
            tick = QGraphicsLineItem(-2, y, 2, y)
            tick.setParentItem(self)

        # prediction marker
        self.dot = Continuous2DMovableDotItem(
            self.dot_r, scale, offset, values[0], values[-1], y_start, y_stop)
        self.dot.tooltip_labels = labels
        self.dot.tooltip_values = values
        self.dot.setParentItem(self)
        h_line = QGraphicsLineItem(values[0] * scale + offset, self.y_diff / 2,
                                   values[-1] * scale + offset, self.y_diff / 2)
        pen = QPen(Qt.DashLine)
        pen.setBrush(QColor(Qt.red))
        h_line.setPen(pen)
        h_line.setParentItem(self)
        self.dot.horizontal_line = h_line

        # line
        line = QGraphicsLineItem(values[0] * scale + offset, y_start,
                                 values[-1] * scale + offset, y_stop)
        line.setParentItem(self)

        # ticks
        for value in values:
            k = (value - values[0]) / (values[-1] - values[0])
            y_tick = (y_stop - y_start) * k + y_start - self.tick_height / 2
            x_tick = value * scale - self.tick_width / 2 + offset
            tick = QGraphicsRectItem(
                x_tick, y_tick, self.tick_width, self.tick_height)
            tick.setBrush(QColor(Qt.black))
            tick.setParentItem(self)

        # rect
        rect = QGraphicsRectItem(
            values[0] * scale + offset, -self.y_diff * 0.125,
            values[-1] * scale + offset, self.y_diff * 1.25)
        pen = QPen(Qt.DotLine)
        pen.setBrush(QColor(50, 150, 200, 255))
        rect.setPen(pen)
        rect.setParentItem(self)
        self.setPreferredSize(self.preferredWidth(), self.y_diff * 1.5)


class NomogramItem(QGraphicsWidget):
    def __init__(self):
        super().__init__()
        self._items = []
        self.layout = QGraphicsLinearLayout(Qt.Vertical)
        self.setLayout(self.layout)

    def add_items(self, items):
        self._items = items
        for item in items:
            self.layout.addItem(item)


class SortableNomogramItem(NomogramItem):
    def __init__(self):
        super().__init__()
        self._sorted_items = []

    def add_items(self, items, sort_type=SortBy.NO_SORTING, n_show=None):
        self._items = items
        self.sort(sort_type)
        self.hide(n_show)

    def sort(self, sort_type=SortBy.NO_SORTING):
        if sort_type == SortBy.NAME:
            reverse, key = False, lambda x: x.name.lower()
        elif sort_type == SortBy.ABSOLUTE:
            reverse, key = True, lambda x: x.diff
        elif sort_type == SortBy.POSITIVE:
            reverse, key = True, lambda x: x.max_value
        elif sort_type == SortBy.NEGATIVE:
            reverse, key = False, lambda x: x.min_value
        self._sorted_items = self._items if sort_type == SortBy.NO_SORTING \
            else sorted(self._items, key=key, reverse=reverse)
        for item in self._sorted_items:
            self.layout.addItem(item)

    def hide(self, n):
        items = self._sorted_items or self._items
        for i, item in enumerate(items):
            item.show()
            if n is not None and i >= n:
                item.hide()
        self.resize(self.preferredSize())
        parent = self.parentWidget()
        if parent:
            parent.resize(parent.preferredSize())


class OWNomogram(OWWidget):
    name = "Nomogram"
    description = " Nomograms for Visualization of Naive Bayesian" \
                  " and Logistic Regression Classifiers."
    icon = "icons/Nomogram.svg"
    priority = 2000

    inputs = [("Classifier", Model, "set_classifier"),
              ("Data", Table, "set_instance")]

    MAX_N_ATTRS = 50
    POINT_SCALE = 0
    ALIGN_LEFT = 0
    ACCEPTABLE = (NaiveBayesModel, LogisticRegressionClassifier)
    settingsHandler = DomainContextHandler()
    target_class_index = ContextSetting(0)
    align = Setting(1)
    scale = Setting(1)
    display_index = Setting(0)
    n_attributes = Setting(5)
    sort_index = Setting(0)
    cont_feature_dim_index = Setting(0)

    graph_name = "scene"

    class Error(OWWidget.Error):
        invalid_classifier = Msg("Nomogram accepts only Naive Bayes and "
                                 "Logistic Regression classifiers.")

    def __init__(self):
        super().__init__()
        self.instances = None
        self.domain = None
        self.data = None
        self.classifier = None
        self.log_odds_ratios = []
        self.log_reg_coeffs = []
        self.log_reg_coeffs_orig = []
        self.log_reg_cont_data_extremes = []
        self.p = None
        self.b0 = None
        self.points = []
        self.feature_items = []
        self.feature_marker_values = []
        self.scale_back = lambda x: x
        self.scale_forth = lambda x: x
        self.nomogram = None
        self.nomogram_main = None
        self.vertical_line = None
        self.hidden_vertical_line = None
        self.old_target_class_index = self.target_class_index

        # GUI
        self.class_combo = gui.comboBox(
            self.controlArea, self, "target_class_index", "Target class",
            callback=self._class_combo_changed, contentsLength=12)

        self.scale_radio = gui.radioButtons(
            self.controlArea, self, "scale", ["Point scale", "Log odds ratios"],
            box="Scale", callback=self._radio_button_changed)

        box = gui.vBox(self.controlArea, "Display features")
        grid = QGridLayout()
        self.display_radio = gui.radioButtonsInBox(
            box, self, "display_index", [], orientation=grid,
            callback=self._display_radio_button_changed)
        radio_all = gui.appendRadioButton(
            self.display_radio, "All:", addToLayout=False)
        radio_best = gui.appendRadioButton(
            self.display_radio, "Best ranked:", addToLayout=False)
        spin_box = gui.hBox(None, margin=0)
        self.n_spin = gui.spin(
            spin_box, self, "n_attributes", 1, 20, label=" ",
            controlWidth=60, callback=self._n_spin_changed)
        grid.addWidget(radio_all, 1, 1)
        grid.addWidget(radio_best, 2, 1)
        grid.addWidget(spin_box, 2, 2)

        self.sort_combo = gui.comboBox(
            box, self, "sort_index", label="Sort by: ", items=SortBy.items(),
            orientation=Qt.Horizontal, callback=self._sort_combo_changed)

        self.cont_feature_dim_combo = gui.comboBox(
            box, self, "cont_feature_dim_index", label="Continuous features: ",
            items=["1D projection", "2D curve"], orientation=Qt.Horizontal,
            callback=self._cont_feature_dim_combo_changed)

        gui.rubber(self.controlArea)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(
            self.scene, horizontalScrollBarPolicy=Qt.ScrollBarAlwaysOff,
            renderHints=QPainter.Antialiasing | QPainter.TextAntialiasing |
                        QPainter.SmoothPixmapTransform, alignment=Qt.AlignLeft)
        self.view.viewport().installEventFilter(self)
        self.view.viewport().setMinimumWidth(300)
        self.mainArea.layout().addWidget(self.view)

    def _class_combo_changed(self):
        values = [item.dot.value for item in self.feature_items]
        self.feature_marker_values = self.scale_back(values)
        coeffs = [np.nan_to_num(p[self.target_class_index] /
                                p[self.old_target_class_index])
                  for p in self.points]
        points = [p[self.old_target_class_index] for p in self.points]
        self.feature_marker_values = [
            self.get_points_from_coeffs(v, c, p) for (v, c, p) in
            zip(self.feature_marker_values, coeffs, points)]
        self.update_scene()
        self.old_target_class_index = self.target_class_index

    def _radio_button_changed(self):
        values = [item.dot.value for item in self.feature_items]
        self.feature_marker_values = self.scale_back(values)
        self.update_scene()

    def _display_radio_button_changed(self):
        self.__hide_attrs(self.n_attributes if self.display_index else None)

    def _n_spin_changed(self):
        self.display_index = 1
        self.__hide_attrs(self.n_attributes)

    def __hide_attrs(self, n_show):
        self.nomogram_main.hide(n_show)
        if self.vertical_line:
            x = self.vertical_line.line().x1()
            y = self.nomogram_main.layout.preferredHeight() + 30
            self.vertical_line.setLine(x, -6, x, y)
            self.hidden_vertical_line.setLine(x, -6, x, y)
        self.scene.setSceneRect(QRectF(self.scene.sceneRect().x(),
                                       self.scene.sceneRect().y(),
                                       self.scene.itemsBoundingRect().width(),
                                       self.nomogram.preferredSize().height()))

    def _sort_combo_changed(self):
        self.nomogram_main.hide(None)
        self.nomogram_main.sort(self.sort_index)
        self.__hide_attrs(self.n_attributes if self.display_index else None)

    def _cont_feature_dim_combo_changed(self):
        values = [item.dot.value for item in self.feature_items]
        self.feature_marker_values = self.scale_back(values)
        self.update_scene()

    def eventFilter(self, obj, event):
        if obj is self.view.viewport() and event.type() == QEvent.Resize:
            values = [item.dot.value for item in self.feature_items]
            self.feature_marker_values = self.scale_back(values)
            self.update_scene()
        return super().eventFilter(obj, event)

    def update_controls(self):
        self.class_combo.clear()
        self.cont_feature_dim_combo.setEnabled(True)
        if self.domain:
            self.class_combo.addItems(self.domain.class_vars[0].values)
            if len(self.domain.attributes) > self.MAX_N_ATTRS:
                self.display_index = 1
            if not self.domain.has_continuous_attributes():
                self.cont_feature_dim_combo.setEnabled(False)
                self.cont_feature_dim_index = 0
        model = self.sort_combo.model()
        item = model.item(SortBy.POSITIVE)
        item.setFlags(item.flags() | Qt.ItemIsEnabled)
        item = model.item(SortBy.NEGATIVE)
        item.setFlags(item.flags() | Qt.ItemIsEnabled)
        if self.classifier and isinstance(self.classifier,
                                          LogisticRegressionClassifier):
            self.align = 0
            item = model.item(SortBy.POSITIVE)
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            item = model.item(SortBy.NEGATIVE)
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            if self.sort_index in (SortBy.POSITIVE, SortBy.POSITIVE):
                self.sort_index = SortBy.NO_SORTING

    def set_instance(self, data):
        self.instances = data
        self.feature_marker_values = []
        self.set_feature_marker_values()

    def set_classifier(self, classifier):
        self.closeContext()
        self.classifier = classifier
        self.Error.clear()
        if self.classifier and not isinstance(self.classifier, self.ACCEPTABLE):
            self.Error.invalid_classifier()
            self.classifier = None
        self.domain = self.classifier.domain if self.classifier else None
        self.update_controls()
        self.openContext(self.domain)
        self.calculate_log_odds_ratios()
        self.calculate_log_reg_coefficients()
        self.points = self.log_odds_ratios or self.log_reg_coeffs
        self.feature_marker_values = []
        self.old_target_class_index = self.target_class_index
        self.update_scene()

    def calculate_log_odds_ratios(self):
        self.log_odds_ratios = []
        self.p = None
        if self.classifier is None or self.domain is None:
            return
        if not isinstance(self.classifier, NaiveBayesModel):
            return

        log_cont_prob = self.classifier.log_cont_prob
        class_prob = self.classifier.class_prob
        for i in range(len(self.domain.attributes)):
            ca = np.exp(log_cont_prob[i]) * class_prob[:, None]
            _or = (ca / (1 - ca)) / (class_prob / (1 - class_prob))[:, None]
            self.log_odds_ratios.append(np.log(_or))
        self.p = class_prob

    def calculate_log_reg_coefficients(self):
        self.log_reg_coeffs = []
        self.log_reg_cont_data_extremes = []
        self.b0 = None
        if self.classifier is None or self.domain is None:
            return
        if not isinstance(self.classifier, LogisticRegressionClassifier):
            return

        self.domain = self.reconstruct_domain(self.classifier.original_domain,
                                              self.domain)
        self.data = Table.from_table(self.domain, self.classifier.original_data)
        attrs, ranges, start = self.domain.attributes, [], 0
        for attr in attrs:
            stop = start + len(attr.values) if attr.is_discrete else start + 1
            ranges.append(slice(start, stop))
            start = stop

        self.b0 = self.classifier.intercept
        coeffs = self.classifier.coefficients
        if len(self.domain.class_var.values) == 2:
            self.b0 = np.hstack((self.b0 * (-1), self.b0))
            coeffs = np.vstack((coeffs * (-1), coeffs))
        self.log_reg_coeffs = [coeffs[:, ranges[i]] for i in range(len(attrs))]
        self.log_reg_coeffs_orig = self.log_reg_coeffs.copy()

        for i in range(len(self.log_reg_coeffs)):
            if self.log_reg_coeffs[i].shape[1] == 1:
                coef = self.log_reg_coeffs[i]
                min_t = np.nanmin(self.data.X, axis=0)[i]
                max_t = np.nanmax(self.data.X, axis=0)[i]
                self.log_reg_coeffs[i] = np.hstack((coef * min_t, coef * max_t))
                self.log_reg_cont_data_extremes.append(
                    [sorted([min_t, max_t], reverse=(c < 0)) for c in coef])
            else:
                self.log_reg_cont_data_extremes.append([None])

    def update_scene(self):
        self.clear_scene()
        if self.domain is None:
            return

        name_items = [QGraphicsTextItem(a.name) for a in self.domain.attributes]
        point_text = QGraphicsTextItem("Points")
        total_text = QGraphicsTextItem("Total")
        probs_text = QGraphicsTextItem("Probabilities")
        all_items = name_items + [point_text, total_text, probs_text]
        name_offset = -max(t.boundingRect().width() for t in all_items) - 50
        w = self.view.viewport().rect().width()
        max_width = w + name_offset - 100

        points = [pts[self.target_class_index] for pts in self.points]
        minimums = [min(p) for p in points]
        if self.align == OWNomogram.ALIGN_LEFT:
            points = [p - m for m, p in zip(minimums, points)]
        d = 100 / max(max(abs(p)) for p in points)
        if self.scale == OWNomogram.POINT_SCALE:
            points = [p * d for p in points]

        if self.scale == OWNomogram.POINT_SCALE and \
                self.align == OWNomogram.ALIGN_LEFT:
            self.scale_back = lambda x: [p / d + m for m, p in zip(minimums, x)]
            self.scale_forth = lambda x: [(p - m) * d for m, p
                                          in zip(minimums, x)]
        if self.scale == OWNomogram.POINT_SCALE and \
                self.align != OWNomogram.ALIGN_LEFT:
            self.scale_back = lambda x: [p / d for p in x]
            self.scale_forth = lambda x: [p * d for p in x]
        if self.scale != OWNomogram.POINT_SCALE and \
                self.align == OWNomogram.ALIGN_LEFT:
            self.scale_back = lambda x: [p + m for m, p in zip(minimums, x)]
            self.scale_forth = lambda x: [p - m for m, p in zip(minimums, x)]
        if self.scale != OWNomogram.POINT_SCALE and \
                self.align != OWNomogram.ALIGN_LEFT:
            self.scale_back = lambda x: x
            self.scale_forth = lambda x: x

        point_item, nomogram_head = self.create_main_nomogram(
            name_items, points, max_width, point_text, name_offset)
        total_item, probs_item, nomogram_foot = self.create_footer_nomogram(
            total_text, probs_text, d, minimums, max_width, name_offset)
        for item in self.feature_items:
            item.dot.point_dot = point_item.dot
            item.dot.total_dot = total_item.dot
            item.dot.probs_dot = probs_item.dot
            item.dot.vertical_line = self.hidden_vertical_line

        self.nomogram = nomogram = NomogramItem()
        nomogram.add_items([nomogram_head, self.nomogram_main, nomogram_foot])
        self.scene.addItem(nomogram)
        self.set_feature_marker_values()
        self.scene.setSceneRect(QRectF(self.scene.itemsBoundingRect().x(),
                                       self.scene.itemsBoundingRect().y(),
                                       self.scene.itemsBoundingRect().width(),
                                       self.nomogram.preferredSize().height()))

    def create_main_nomogram(self, name_items, points, max_width, point_text,
                             name_offset):
        cls_index = self.target_class_index
        min_p = min(min(p) for p in points)
        max_p = max(max(p) for p in points)
        values = self.get_ruler_values(min_p, max_p, max_width)
        min_p, max_p = min(values), max(values)
        scale_x = max_width / (max_p - min_p)

        nomogram_header = NomogramItem()
        point_item = RulerItem(point_text, values, scale_x, name_offset,
                               - scale_x * min_p, title="Points")
        point_item.setPreferredSize(point_item.preferredWidth(), 35)
        nomogram_header.add_items([point_item])

        self.nomogram_main = SortableNomogramItem()
        cont_feature_item_class = ContinuousFeature2DItem if \
            self.cont_feature_dim_index else ContinuousFeatureItem
        self.feature_items = [
            DiscreteFeatureItem(
                name_items[i], [val for val in att.values], points[i],
                scale_x, name_offset, - scale_x * min_p,
                self.points[i][cls_index]) if att.is_discrete else
            cont_feature_item_class(
                name_items[i], self.log_reg_cont_data_extremes[i][cls_index],
                self.get_ruler_values(
                    np.min(points[i]), np.max(points[i]),
                    scale_x * (np.max(points[i]) - np.min(points[i])), False),
                scale_x, name_offset, - scale_x * min_p,
                self.log_reg_coeffs_orig[i][cls_index][0])
            for i, att in enumerate(self.domain.attributes)]
        self.nomogram_main.add_items(
            self.feature_items, self.sort_index,
            self.n_attributes if self.display_index else None)

        x = - scale_x * min_p
        y = self.nomogram_main.layout.preferredHeight() + 30
        self.vertical_line = QGraphicsLineItem(x, -6, x, y)
        self.vertical_line.setPen(QPen(Qt.DotLine))
        self.vertical_line.setParentItem(point_item)
        self.hidden_vertical_line = QGraphicsLineItem(x, -6, x, y)
        pen = QPen(Qt.DashLine)
        pen.setBrush(QColor(Qt.red))
        self.hidden_vertical_line.setPen(pen)
        self.hidden_vertical_line.setParentItem(point_item)

        return point_item, nomogram_header

    def create_footer_nomogram(self, total_text, probs_text, d, minimums,
                               max_width, name_offset):
        eps, d_ = 0.05, 1
        k = - np.log(self.p / (1 - self.p)) if self.p is not None else - self.b0
        min_sum = k[self.target_class_index] - np.log((1 - eps) / eps)
        max_sum = k[self.target_class_index] - np.log(eps / (1 - eps))
        if self.align == OWNomogram.ALIGN_LEFT:
            max_sum = max_sum - sum(minimums)
            min_sum = min_sum - sum(minimums)
            for i in range(len(k)):
                k[i] = k[i] - sum([min(q) for q in [p[i] for p in self.points]])
        if self.scale == OWNomogram.POINT_SCALE:
            min_sum *= d
            max_sum *= d
            d_ = d

        values = self.get_ruler_values(min_sum, max_sum, max_width)
        min_sum, max_sum = min(values), max(values)
        scale_x = max_width / (max_sum - min_sum)
        cls_var, cls_index = self.domain.class_var, self.target_class_index
        nomogram_footer = NomogramItem()
        total_item = RulerItem(total_text, values, scale_x, name_offset,
                               - scale_x * min_sum, title="Total")
        probs_item = RulerItem(
            probs_text, values, scale_x, name_offset, - scale_x * min_sum,
            title="P({}='{}')".format(cls_var.name, cls_var.values[cls_index]),
            get_probabilities=lambda f: 1 / (1 + np.exp(k[cls_index] - f / d_)))
        nomogram_footer.add_items([total_item, probs_item])
        return total_item, probs_item, nomogram_footer

    def set_feature_marker_values(self):
        if not (len(self.points) and len(self.feature_items)):
            return
        if not len(self.feature_marker_values):
            self._init_feature_marker_values()
        self.feature_marker_values = self.scale_forth(
            self.feature_marker_values)
        item = self.feature_items[0]
        for i, item in enumerate(self.feature_items):
            item.dot.move_to_val(self.feature_marker_values[i])
        item.dot.total_dot.move_to_sum()
        item.dot.probs_dot.move_to_sum()

    def _init_feature_marker_values(self):
        self.feature_marker_values = []
        cls_index = self.target_class_index
        for i, attr in enumerate(self.domain.attributes):
            value, feature_val = 0, None
            if len(self.log_reg_coeffs):
                if attr.is_discrete:
                    ind, n = np.unique(self.data.X[:, i], return_counts=True)
                    feature_val = np.nan_to_num(ind[np.argmax(n)])
                else:
                    feature_val = np.average(self.data.X[:, i])
            inst_in_dom = self.instances and attr in self.instances.domain
            if inst_in_dom and not np.isnan(self.instances[0][attr]):
                feature_val = self.instances[0][attr]
            if feature_val is not None:
                value = self.points[i][cls_index][int(feature_val)] \
                    if attr.is_discrete else \
                    self.log_reg_coeffs_orig[i][cls_index][0] * feature_val
            self.feature_marker_values.append(value)

    def clear_scene(self):
        self.scene.clear()

    def send_report(self):
        self.report_plot()

    @staticmethod
    def reconstruct_domain(original, preprocessed):
        attrs = []
        for attr in preprocessed.attributes:
            cv = attr._compute_value.variable._compute_value
            var = cv.variable if cv else original[attr.name]
            if var in attrs:
                continue
            attrs.append(var)
        return Domain(attrs, original.class_var, original.metas)

    @staticmethod
    def get_ruler_values(start, stop, max_width, round_to_nearest=True):
        diff = (stop - start) / max_width
        if diff <= 0:
            return [0]
        decimals = int(np.floor(np.log10(diff)))
        if diff > 8 * pow(10, decimals):
            step = 5 * pow(10, decimals + 2)
        elif diff > 4 * pow(10, decimals):
            step = 2 * pow(10, decimals + 2)
        elif diff > 2 * pow(10, decimals):
            step = 1 * pow(10, decimals + 2)
        else:
            step = 5 * pow(10, decimals + 1)
        round_by = int(- np.floor(np.log10(step)))
        r = start % step
        if not round_to_nearest:
            _range = np.arange(start + step, stop + r, step) - r
            start, stop = np.floor(start * 100) / 100, np.ceil(stop * 100) / 100
            return np.round(np.hstack((start, _range, stop)), 2)
        return np.round(np.arange(start, stop + r + step, step) - r, round_by)

    @staticmethod
    def get_points_from_coeffs(current_value, coefficients, possible_values):
        indices = np.argsort(possible_values)
        sorted_values = possible_values[indices]
        sorted_coefficients = coefficients[indices]
        for i, val in enumerate(sorted_values):
            if current_value < val:
                break
        diff = sorted_values[i] - sorted_values[i - 1]
        k = 0 if diff < 1e-6 else (sorted_values[i] - current_value) / \
                                  (sorted_values[i] - sorted_values[i - 1])
        return sorted_coefficients[i - 1] * sorted_values[i - 1] * k + \
               sorted_coefficients[i] * sorted_values[i] * (1 - k)


if __name__ == "__main__":
    from Orange.classification import NaiveBayesLearner, \
        LogisticRegressionLearner
    from AnyQt.QtWidgets import QApplication

    app = QApplication([])
    ow = OWNomogram()
    titanic = Table("titanic")
    clf = NaiveBayesLearner()(titanic)
    # clf = LogisticRegressionLearner()(titanic)
    ow.set_classifier(clf)
    ow.set_instance(titanic[0:])
    ow.show()
    app.exec_()
    ow.saveSettings()
