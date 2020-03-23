@Ui('errors.xml')
class ErrorViewModel(ViewModel):
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ErrorViewModel()
        return cls._instance

    err_list : wx.ListCtrl
    _instance = None

    def initialize(self):
        self.file_headers = ['File', 'Node', 'Parent', 'Error', 'Error Text']
        self.msg_detail = []
        self.selection = bind.BindValue(0)

    def get_message_detail(self, v: int):
        if 0 <= v < len(self.msg_detail):
            return str(self.msg_detail[v])
        else:
            return ''

    def row_select_str(self, v: int):
        if v >= 0:
            return 'Error %d' % (v + 1)
        else:
            return ''

    def ready(self):
        self.err_list = self.view.widgets['error_list']

    @invoke_ui
    def add_error(self, node, filename, parent, exception, tb):
        self.err_list.AppendItem([
            filename,
            getattr(node, 'tag', node),
            parent.__class__.__name__,
            exception.__class__.__name__,
            str(exception)
        ], self.err_list.GetItemCount())
        self.msg_detail.append(tb)

        # go ahead and select the first row, if this is the first item
        if self.err_list.SelectedRow == -1:
            self.err_list.SelectRow(0)

    @invoke_ui
    def clear(self):
        self.err_list.Freeze()
        self.err_list.DeleteAllItems()
        self.err_list.Thaw()
        self.msg_detail = []
        #self.err_list.UnselectRow(self.selection.value)