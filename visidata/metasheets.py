from visidata import globalCommand, Sheet, Column, options, Colorizer, vd, error, anytype, ENTER, asyncthread, status, Progress
from visidata import ColumnAttr, ColumnEnum, ColumnItem
from visidata import getGlobals, TsvSheet, Path, bindkeys, commands

globalCommand('gC', 'columns-all', 'vd.push(ColumnsSheet("all_columns", source=vd.sheets))')
globalCommand('S', 'sheets', 'vd.push(vd.sheetsSheet)')
globalCommand('gS', 'sheets-graveyard', 'vd.push(vd.graveyardSheet).reload()')

Sheet.addCommand('O', 'options-sheet', 'vd.push(getOptionsSheet(sheet)).reload()')
Sheet.addCommand('gO', 'options-global', 'vd.push(vd.optionsSheet)')
Sheet.addCommand('C', 'columns-sheet', 'vd.push(ColumnsSheet(name+"_columns", source=[sheet]))')
Sheet.addCommand('z^H', 'help-commands', 'vd.push(HelpSheet(name + "_commands", source=sheet, revbinds={}))')


def getOptionsSheet(sheet):
    optsheet = getattr(sheet, 'optionsSheet', None)
    if not optsheet:
        sheet.optionsSheet = OptionsSheet(sheet.name+"_options", source=sheet)

    return sheet.optionsSheet


class ColumnsSheet(Sheet):
    rowtype = 'columns'
    precious = False
    class ValueColumn(Column):
        'passthrough to the value on the source cursorRow'
        def calcValue(self, srcCol):
            return srcCol.getDisplayValue(srcCol.sheet.cursorRow)
        def setValue(self, srcCol, val):
            srcCol.setValue(self.sheet.source.cursorRow, val)

    columns = [
            ColumnAttr('sheet', type=str),
            ColumnAttr('name', width=options.default_width),
            ColumnAttr('width', type=int),
            ColumnEnum('type', getGlobals(), default=anytype),
            ColumnAttr('fmtstr'),
            ValueColumn('value', width=options.default_width),
            Column('expr', getter=lambda col,row: getattr(row, 'expr', None),
                           setter=lambda col,row,val: setattr(row, 'expr', val)),
    ]
    nKeys = 2
    colorizers = Sheet.colorizers + [
            Colorizer('row', 7, lambda self,c,r,v: options.color_key_col if r.keycol else None),
            Colorizer('row', 6, lambda self,c,r,v: options.color_hidden_col if r.hidden else None),
    ]
    def reload(self):
        if len(self.source) == 1:
            self.rows = self.source[0].columns
            self.cursorRowIndex = self.source[0].cursorColIndex
            self.columns[0].hide()  # hide 'sheet' column if only one sheet
        else:
            self.rows = [col for vs in self.source for col in vs.visibleCols if vs is not self]

ColumnsSheet.addCommand(None, 'resize-source-rows-max', 'for c in selectedRows or [cursorRow]: c.width = c.getMaxWidth(source.visibleRows)')
ColumnsSheet.addCommand('&', 'join-cols', 'rows.insert(cursorRowIndex, combineColumns(selectedRows or error("no columns selected to concatenate")))')


class SheetsSheet(Sheet):
    rowtype = 'sheets'
    precious = False
    columns = [
        ColumnAttr('name', width=30),
        ColumnAttr('nRows', type=int),
        ColumnAttr('nCols', type=int),
        ColumnAttr('nVisibleCols', type=int),
        ColumnAttr('cursorDisplay'),
        ColumnAttr('keyColNames'),
        ColumnAttr('source'),
        ColumnAttr('progressPct'),
    ]
    nKeys = 1

    def newRow(self):
        return Sheet('', columns=[ColumnItem('', 0)], rows=[])

    def reload(self):
        self.rows = self.source

SheetsSheet.addCommand(ENTER, 'open-row', 'dest=cursorRow; vd.sheets.remove(sheet) if not sheet.precious else None; vd.push(dest)')
SheetsSheet.addCommand('g'+ENTER, 'open-rows', 'for vs in selectedRows: vd.push(vs)')
SheetsSheet.addCommand('g^R', 'reload-selected', 'for vs in selectedRows or rows: vs.reload()')
SheetsSheet.addCommand('gC', 'columns-selected', 'vd.push(ColumnsSheet("all_columns", source=selectedRows or rows[1:]))')
SheetsSheet.addCommand('gI', 'describe-selected', 'vd.push(DescribeSheet("describe_all", source=selectedRows or rows[1:]))')

# source: vd.allSheets (with BaseSheet as weakref keys)
class GraveyardSheet(SheetsSheet):
    rowtype = 'dead sheets'  # rowdef: BaseSheet
    def reload(self):
        self.rows = list(vs for vs in self.source.keys() if vs not in vd().sheets)


class HelpSheet(Sheet):
    'Show all commands available to the source sheet.'
    rowtype = 'commands'
    precious = False

    columns = [
        ColumnAttr('sheet'),
        ColumnAttr('longname'),
        Column('keystrokes', getter=lambda col,row: col.sheet.revbinds.get(row.longname)),
        Column('helpstr', getter=lambda col,row: col.sheet.cmddict[(row.sheet, row.longname)].helpstr),
        ColumnAttr('execstr', width=0),
        ColumnAttr('logged', 'replayable', width=0),
    ]
    nKeys = 2
    def reload(self):
        from pkg_resources import resource_filename
        cmdlist = TsvSheet('cmdlist', source=Path(resource_filename(__name__, 'commands.tsv')))
        cmdlist.reload_sync()
        self.cmddict = {}
        for cmdrow in cmdlist.rows:
            self.cmddict[(cmdrow.sheet, cmdrow.longname)] = cmdrow

        self.revbinds = {
            longname:keystrokes
                for (keystrokes, _), longname in bindkeys.iter(self.source)
                    if keystrokes not in self.revbinds
        }
        self.rows = []
        for (k, o), v in commands.iter(self.source):
            self.addRow(v)
            v.sheet = o

class OptionsSheet(Sheet):
    rowtype = 'options'
    precious = False
    columns = (
       ColumnAttr('name'),
       Column('sheet_value', getter=lambda col,row: options.get(row.name, col.sheet.source),
                             setter=lambda col,row,val: options.set(row.name, val, col.sheet.source)),
       Column('override', getter=lambda col,row: options._opts.get((row.name, 'override'), ''),
                          setter=lambda col,row,val: options.set(row.name, val, 'override')),
       Column('default', getter=lambda col,row: options.get(row.name, 'global')),
       ColumnAttr('helpstr')
    )

    colorizers = Sheet.colorizers + [
        Colorizer('cell', 9, lambda s,c,r,v: v.value if c.name in ['sheet_value', 'override', 'default'] and r.name.startswith('color_') else None)
    ]

    nKeys=1

    def reload(self):
        self.rows = []
        for k in options.keys():
            opt = options._get(k)
            self.addRow(opt)

vd().optionsSheet = OptionsSheet('global_options', source=None)
vd().sheetsSheet = SheetsSheet("sheets", source=vd().sheets)
vd().graveyardSheet = GraveyardSheet("sheets_graveyard", source=vd().allSheets)


def combineColumns(cols):
    'Return Column object formed by joining fields in given columns.'
    return Column("+".join(c.name for c in cols),
                  getter=lambda col,row,cols=cols,ch=' ': ch.join(c.getDisplayValue(row) for c in cols))

# used ColumnsSheet, affecting the 'row' (source column)
ColumnsSheet.addCommand('g!', 'key-selected', 'setKeys(selectedRows or [cursorRow])')
ColumnsSheet.addCommand('gz!', 'key-off-selected', 'unsetKeys(selectedRows or [cursorRow])')
ColumnsSheet.addCommand('g-', 'hide-selected', 'for c in selectedRows or [cursorRow]: c.hide()')
ColumnsSheet.addCommand('g%', 'type-float-selected', 'for c in selectedRows or [cursorRow]: c.type = float')
ColumnsSheet.addCommand('g#', 'type-int-selected', 'for c in selectedRows or [cursorRow]: c.type = int')
ColumnsSheet.addCommand('gz#', 'type-len-selected', 'for c in selectedRows or [cursorRow]: c.type = len')
ColumnsSheet.addCommand('g@', 'type-date-selected', 'for c in selectedRows or [cursorRow]: c.type = date')
ColumnsSheet.addCommand('g$', 'type-currency-selected', 'for c in selectedRows or [cursorRow]: c.type = currency')
ColumnsSheet.addCommand('g~', 'type-string-selected', 'for c in selectedRows or [cursorRow]: c.type = str')
ColumnsSheet.addCommand('gz~', 'type-any-selected', 'for c in selectedRows or [cursorRow]: c.type = anytype')

