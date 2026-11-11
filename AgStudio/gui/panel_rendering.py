"""Qt-only keyed reconciliation. Feature derivation lives in child processes."""
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTreeWidgetItem

from .finding_list import FindingItem, finding_update


def _detach(tree, item):
    parent = item.parent()
    if parent is None:
        return tree.takeTopLevelItem(tree.indexOfTopLevelItem(item))
    return parent.takeChild(parent.indexOfChild(item))


def apply_outline(tab, projection):
    tree = tab.outline
    blocker = QSignalBlocker(tree)
    scroll = tree.verticalScrollBar().value()
    selected = tree.currentItem()
    selected_key = selected.data(0, Qt.ItemDataRole.UserRole + 1) if selected else None
    old = getattr(tab, '_outline_by_key', {})
    wanted = {row.key for row in projection.rows}
    # Remove children before their parents; surviving objects are never destroyed.
    for key in sorted(set(old) - wanted, key=len, reverse=True):
        _detach(tree, old.pop(key))
    items, spans, positions = {}, {}, {}
    root = tree.invisibleRootItem()
    for row in projection.rows:
        item = old.get(row.key)
        fresh = item is None
        if fresh:
            item = QTreeWidgetItem()
            old[row.key] = item
        for column, text in enumerate((row.label, row.line)):
            if item.text(column) != text:
                item.setText(column, text)
        if item.toolTip(0) != row.tooltip:
            item.setToolTip(0, row.tooltip)
        if item.data(0, Qt.ItemDataRole.UserRole) != row.fact_id:
            item.setData(0, Qt.ItemDataRole.UserRole, row.fact_id)
        if fresh:
            item.setData(0, Qt.ItemDataRole.UserRole + 1, row.key)
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator if row.literal
                                         else QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless)
        if fresh or item.data(0, Qt.ItemDataRole.UserRole + 2) != row.role:
            item.setData(0, Qt.ItemDataRole.UserRole + 2, row.role)
            color = QColor(*tab.editor.color_scheme[row.role]['foreground'])
            for column in range(2):
                item.setForeground(column, color)
        parent = old[row.parent_key] if row.parent_key else root
        index = positions.get(row.parent_key, 0)
        positions[row.parent_key] = index + 1
        if parent.indexOfChild(item) != index:
            if item.treeWidget() is tree:
                _detach(tree, item)
            parent.insertChild(index, item)
        if fresh:
            item.setExpanded(row.key in tab._outline_expanded)
        items[row.fact_id] = item
        spans[row.fact_id] = row.span
    tab._outline_by_key = old
    tab._outline_items = items
    tab._context_spans = spans
    tab._context_line_starts = projection.line_starts
    tab._outline_document_id = projection.document_id
    tab._outline_current = True
    if selected_key in old:
        tree.setCurrentItem(old[selected_key])
    tree.verticalScrollBar().setValue(scroll)
    del blocker
    tab.outline_spinner.set_pending(False)
    tab.outline_status.setText('')
    tab.outline_status.setToolTip('')
    tab._update_outline_toggle()
    # Preserve explicit selection across publication. Only initial render follows caret.
    if selected_key not in old:
        tab._sync_context()
    elif tree.currentItem() is not None:
        tab._highlight_context(tree.currentItem())


def apply_findings(tab, projection):
    with finding_update(tab.diagnostic_list) as sorting:
        _apply_findings(tab, projection, sorting)


def _apply_findings(tab, projection, sorting):
    from .app import FINDING_ICONS, _finding_icon
    tree = tab.diagnostic_list
    blocker = QSignalBlocker(tree)
    scroll = tree.verticalScrollBar().value()
    old = getattr(tab, '_finding_by_key', {})
    wanted = {row.key for row in projection.rows}
    for key in set(old) - wanted:
        _detach(tree, old.pop(key))
    icons = getattr(tab, '_finding_icons', None)
    if icons is None:
        icons = tab._finding_icons = {severity: _finding_icon(tab.style(), severity) for severity in FINDING_ICONS}
    order = tuple(row.key for row in projection.rows)
    stable_order = order == getattr(tab, '_finding_order', None)
    batch_blocker = QSignalBlocker(tree.model()) if stable_order else None
    changed_roles = set()
    for index, row in enumerate(projection.rows):
        item = old.get(row.key)
        fresh = item is None
        if fresh:
            item = FindingItem(row.key)
            old[row.key] = item
            item.setIcon(0, icons[row.finding.severity])
        # QTreeWidget emits an unscoped model change for Python UserRole data.
        # ResizeToContents otherwise rescans every row for every finding.
        # Structural insert/remove signals stay live; value changes publish once.
        value_blocker = QSignalBlocker(tree.model()) if not fresh and not stable_order else None
        for column, text in enumerate(row.texts):
            if item.text(column) != text:
                item.setText(column, text)
                changed_roles.add(Qt.ItemDataRole.DisplayRole)
            if item.toolTip(column) != row.tooltip:
                item.setToolTip(column, row.tooltip)
                changed_roles.add(Qt.ItemDataRole.ToolTipRole)
        if item.data(0, Qt.ItemDataRole.UserRole) != row.finding:
            item.setData(0, Qt.ItemDataRole.UserRole, row.finding)
            changed_roles.add(Qt.ItemDataRole.UserRole)
        del value_blocker
        if sorting:
            if item.treeWidget() is not tree:
                tree.addTopLevelItem(item)
        elif tree.indexOfTopLevelItem(item) != index:
            if item.treeWidget() is tree:
                _detach(tree, item)
            tree.insertTopLevelItem(index, item)
    del batch_blocker
    tab._finding_order = order
    if changed_roles and tree.topLevelItemCount():
        model = tree.model()
        model.dataChanged.emit(model.index(0, 0), model.index(tree.topLevelItemCount() - 1, 4),
                               list(changed_roles))
    tab._finding_by_key = old
    tab._findings_document_id = projection.document_id
    tab._findings_current = True
    tree.verticalScrollBar().setValue(scroll)
    del blocker
    tab.editor.set_spelling_ranges(projection.spelling)
    tab._update_finding_counts(tuple(row.finding for row in projection.rows))
    tab.editor.finding_severities = dict(projection.severities)
    tab.editor.finding_lines = frozenset(tab.editor.finding_severities)
    tab.editor.gutter.update()
    tab.diagnostics_heading.setToolTip(projection.heading_tooltip)
