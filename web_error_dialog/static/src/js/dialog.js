odoo.define('web.gooderp_dialog', function(require) {
    var crash_manager = require('web.CrashManager');
    var core = require('web.core');
    var Dialog = require('web.Dialog');
    
    // 自定义填充按钮，一个对象列表。规则如下
    // @text: 按钮的显示文本
    // @classes: 按钮的class
    // @click：参数为点击事件event的函数
    // @close：一个Bool字段，当click属性没值且该值为true的时候点击默认关闭
    
    var warning_buttons = false;
    var error_buttons = false;
    var message_buttons = false;
    var default_buttons = [{text: core._t("Ok"), close: true}];

    crash_manager.include({
        show_warning: function(error) {
            if (!this.active) {
                return;
            }
            new Dialog(this, {
                size: 'medium',
                title: "Odoo " + (_.str.capitalize(error.type) || _t("Warning")),
                subtitle: error.data.title,
                $content: $('<div>').html(core.qweb.render('CrashManager.warning', {error: error})),
                buttons: warning_buttons || default_buttons
            }).open();
        },
        show_error: function(error) {
            if (!this.active) {
                return;
            }
            new Dialog(this, {
                title: "Odoo " + _.str.capitalize(error.type),
                $content: core.qweb.render('CrashManager.error', {error: error}),
                buttons: error.buttons || error_buttons || default_buttons,
            }).open();
        },
        show_message: function(exception) {
            this.show_error({
                type: _t("Client Error"),
                message: exception,
                data: {debug: ""},
                buttons: message_buttons || false,
            });
        },
    })
})