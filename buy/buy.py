# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2016  开阖软件(<http://www.osbzr.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import fields, models, api
import odoo.addons.decimal_precision as dp
from odoo.exceptions import UserError
from datetime import datetime

# 购货订单审核状态可选值
BUY_ORDER_STATES = [
        ('draft', u'未审核'),
        ('done', u'已审核'),
    ]

# 字段只读状态
READONLY_STATES = {
        'done': [('readonly', True)],
    }

class vendor_goods(models.Model):
    _name = 'vendor.goods'

    goods_id = fields.Many2one(
        string=u'商品',
        required=True,
        comodel_name='goods',
        ondelete='cascade',
        help=u'商品',
    )

    vendor_id = fields.Many2one(
        string=u'供应商',
        required=True,
        comodel_name='partner',
        domain=[('s_category_id','!=',False)],
        ondelete='cascade',
        help=u'供应商',
    )
    
    price = fields.Float(u'供货价',
                         digits=dp.get_precision('Amount'),
                         help=u'供应商提供的价格')
    
    code = fields.Char(u'供应商产品编号',
                       help=u'供应商提供的产品编号')

    name = fields.Char(u'供应商产品名称',
                       help=u'供应商提供的产品名称')

    min_qty = fields.Float(u'最低订购量',
                           digits=dp.get_precision('Quantity'),
                           help=u'采购产品时，大于或等于最低订购量时，产品的价格才取该行的供货价')
    

class partner(models.Model):
    _inherit = 'partner'

    goods_ids = fields.One2many(
        string=u'供应产品',
        comodel_name='vendor.goods',
        inverse_name='vendor_id',
        help=u'供应商供应的产品价格列表',
    )


class goods(models.Model):

    _inherit = 'goods' 

    vendor_ids = fields.One2many(
        string=u'供应价格',
        comodel_name='vendor.goods',
        inverse_name='goods_id',
        help=u'各供应商提供的基于最低订购量的供货价格列表',
    )


class buy_order(models.Model):
    _name = "buy.order"
    _inherit = ['mail.thread']
    _description = u"购货订单"
    _order = 'date desc, id desc'

    @api.one
    @api.depends('line_ids.subtotal', 'discount_amount')
    def _compute_amount(self):
        '''当订单行和优惠金额改变时，改变优惠后金额'''
        total = sum(line.subtotal for line in self.line_ids)
        self.amount = total - self.discount_amount

    @api.one
    @api.depends('line_ids.quantity', 'line_ids.quantity_in')
    def _get_buy_goods_state(self):
        '''返回收货状态'''
        if all(line.quantity_in == 0 for line in self.line_ids):
            self.goods_state = u'未入库'
        elif any(line.quantity > line.quantity_in for line in self.line_ids):
            self.goods_state = u'部分入库'
        else:
            self.goods_state = u'全部入库'

    @api.model
    def _default_warehouse_dest(self):
        '''获取默认调入仓库'''
        if self.env.context.get('warehouse_dest_type'):
            return self.env['warehouse'].get_warehouse_by_type(
                        self.env.context.get('warehouse_dest_type'))

        return self.env['warehouse'].browse()

    @api.one
    @api.depends('amount', 'amount_executed')
    def _get_money_state(self):
        '''计算购货订单付款/退款状态'''
        if self.amount_executed == 0:
            self.money_state = (self.type == 'buy') and u'未付款' or u'未退款'
        elif self.amount_executed < self.amount:
            self.money_state = (self.type == 'buy') and u'部分付款' or u'部分退款'
        elif self.amount_executed == self.amount:
            self.money_state = (self.type == 'buy') and u'全部付款' or u'全部退款'

    partner_id = fields.Many2one('partner', u'供应商', states=READONLY_STATES,
                                 ondelete='restrict',
                                 help=u'供应商')
    date = fields.Date(u'单据日期', states=READONLY_STATES,
                       default=lambda self: fields.Date.context_today(self),
                       select=True, copy=False, help=u"默认是订单创建日期")
    planned_date = fields.Date(
                        u'要求交货日期', states=READONLY_STATES,
                        default=lambda self: fields.Date.context_today(self),
                        select=True, copy=False, help=u"订单的要求交货日期")
    name = fields.Char(u'单据编号', select=True, copy=False,
                       help=u"购货订单的唯一编号，当创建时它会自动生成下一个编号。")
    type = fields.Selection([('buy', u'购货'), ('return', u'退货')], u'类型',
                            default='buy', states=READONLY_STATES,
                            help=u'购货订单的类型，分为购货或退货')
    warehouse_dest_id = fields.Many2one('warehouse', u'调入仓库',
                                        default=_default_warehouse_dest,
                                        ondelete='restrict', states=READONLY_STATES,
                                        help=u'将产品调入到该仓库')
    invoice_by_receipt=fields.Boolean(string=u"按收货结算", default=True,
                                      help=u'如未勾选此项，可在资金行里输入付款金额，订单保存后，采购人员可以单击资金行上的【确认】按钮。')
    line_ids = fields.One2many('buy.order.line', 'order_id', u'购货订单行',
                               states=READONLY_STATES, copy=True,
                               help=u'购货订单的明细行，不能为空')
    note = fields.Text(u'备注', help=u'单据备注')
    discount_rate = fields.Float(u'优惠率(%)', states=READONLY_STATES,
                                 digits=dp.get_precision('Amount'),
                                 help=u'整单优惠率')
    discount_amount = fields.Float(u'优惠金额', states=READONLY_STATES,
                                   track_visibility='always',
                                   digits=dp.get_precision('Amount'),
                                   help=u'整单优惠金额，可由优惠率自动计算出来，也可手动输入')
    amount = fields.Float(u'优惠后金额', store=True, readonly=True,
                          compute='_compute_amount', track_visibility='always',
                          digits=dp.get_precision('Amount'),
                          help=u'总金额减去优惠金额')
    prepayment = fields.Float(u'预付款', states=READONLY_STATES,
                           digits=dp.get_precision('Amount'),
                           help=u'输入预付款审核购货订单，会产生一张付款单')
    bank_account_id = fields.Many2one('bank.account', u'结算账户',
                                      ondelete='restrict',
                                      help=u'用来核算和监督企业与其他单位或个人之间的债权债务的结算情况')
    approve_uid = fields.Many2one('res.users', u'审核人',
                                  copy=False, ondelete='restrict',
                                  help=u'审核单据的人')
    state = fields.Selection(BUY_ORDER_STATES, u'审核状态', readonly=True,
                             help=u"购货订单的审核状态", select=True, copy=False,
                             default='draft')
    goods_state = fields.Char(u'收货状态', compute=_get_buy_goods_state,
                              default=u'未入库', store=True,
                              help=u"购货订单的收货状态", select=True, copy=False)
    cancelled = fields.Boolean(u'已终止',
                               help=u'该单据是否已终止')
    pay_ids=fields.One2many("payment.plan","buy_id",string=u"付款计划",
                            help=u'分批付款时使用付款计划')
    amount_executed = fields.Float(u'已执行金额',
                                   help=u'入库单已付款金额或退货单已退款金额')
    money_state = fields.Char(u'付/退款状态',
                              compute=_get_money_state,
                              store=True,
                              help=u'购货订单生成的采购入库单或退货单的付/退款状态')

    @api.onchange('discount_rate', 'line_ids')
    def onchange_discount_rate(self):
        '''当优惠率或购货订单行发生变化时，单据优惠金额发生变化'''
        total = sum(line.subtotal for line in self.line_ids)
        self.discount_amount = total * self.discount_rate * 0.01


    @api.multi
    def unlink(self):
        for order in self:
            if order.state == 'done':
                raise UserError(u'不能删除已审核的单据')

        return super(buy_order, self).unlink()

    def _get_vals(self):
        '''返回创建 money_order 时所需数据'''
        flag = (self.type == 'buy' and 1 or -1) # 用来标志入库或退货
        amount = flag * self.amount
        this_reconcile = flag * self.prepayment
        money_lines = [{
                'bank_id': self.bank_account_id.id,
                'amount': this_reconcile,
            }]
        return {
            'partner_id': self.partner_id.id,
            'date': fields.Date.context_today(self),
            'line_ids':
            [(0, 0, line) for line in money_lines],
            'amount': amount,
            'reconciled': this_reconcile,
            'to_reconcile': amount,
            'state': 'draft',
            'origin_name': self.name,
        }

    @api.one
    def generate_payment_order(self):
        '''由购货订单生成付款单'''
        # 入库单/退货单
        if self.prepayment:
            money_order = self.with_context(type='pay').env['money.order'].create(
                self._get_vals()
            )
            return money_order

    @api.one
    def buy_order_done(self):
        '''审核购货订单'''
        if self.state == 'done':
            raise UserError(u'请不要重复审核！')
        if not self.line_ids:
            raise UserError(u'请输入产品明细行！')
        for line in self.line_ids:
            if line.quantity <= 0 or line.price_taxed < 0:
                raise UserError(u'产品 %s 的数量和含税单价不能小于0！' % line.goods_id.name)
        if self.bank_account_id and not self.prepayment:
            raise UserError(u'结算账户不为空时，需要输入预付款！')
        if not self.bank_account_id and self.prepayment:
            raise UserError(u'预付款不为空时，请选择结算账户！')
        # 采购预付款生成付款单
        self.generate_payment_order()
        self.buy_generate_receipt()
        self.state = 'done'
        self.approve_uid = self._uid

    @api.one
    def buy_order_draft(self):
        '''反审核购货订单'''
        if self.state == 'draft':
            raise UserError(u'请不要重复反审核！')
        if self.goods_state != u'未入库':
            raise UserError(u'该购货订单已经收货，不能反审核！')
        # 查找产生的入库单并删除
        receipt = self.env['buy.receipt'].search(
                         [('order_id', '=', self.name)])
        receipt.unlink()
        #查找产生的付款单并反审核，删除
        money_order = self.env['money.order'].search(
                          [('origin_name','=',self.name)])
        if money_order:
            money_order.money_order_draft()
            money_order.unlink()
        self.state = 'draft'
        self.approve_uid = ''

    @api.one
    def get_receipt_line(self, line, single=False):
        '''返回采购入库/退货单行'''
        qty = 0
        discount_amount = 0
        if single:
            qty = 1
            discount_amount = (line.discount_amount /
                               ((line.quantity - line.quantity_in) or 1))
        else:
            qty = line.quantity - line.quantity_in
            discount_amount = line.discount_amount
        return {
                    'buy_line_id': line.id,
                    'goods_id': line.goods_id.id,
                    'attribute_id': line.attribute_id.id,
                    'goods_uos_qty': line.goods_id.conversion and qty / line.goods_id.conversion or qty,
                    'uos_id': line.goods_id.uos_id.id,
                    'goods_qty': qty,
                    'uom_id': line.uom_id.id,
                    'cost_unit': line.price,
                    'price_taxed': line.price_taxed,
                    'discount_rate': line.discount_rate,
                    'discount_amount': discount_amount,
                    'tax_rate': line.tax_rate,
                    'note': line.note or '',
                }

    def _generate_receipt(self, receipt_line):
        '''根据明细行生成入库单或退货单'''
        # 如果退货，warehouse_dest_id，warehouse_id要调换
        warehouse = (self.type == 'buy'
                     and self.env.ref("warehouse.warehouse_supplier")
                     or self.warehouse_dest_id)
        warehouse_dest = (self.type == 'buy'
                          and self.warehouse_dest_id
                          or self.env.ref("warehouse.warehouse_supplier"))
        rec = (self.type == 'buy' and self.with_context(is_return=False)
               or self.with_context(is_return=True))
        receipt_id = rec.env['buy.receipt'].create({
            'partner_id': self.partner_id.id,
            'warehouse_id': warehouse.id,
            'warehouse_dest_id': warehouse_dest.id,
            'date': self.planned_date,
            'date_due': fields.Date.context_today(self),
            'order_id': self.id,
            'origin': 'buy.receipt',
            'note': self.note,
            'discount_rate': self.discount_rate,
            'discount_amount': self.discount_amount,
            'invoice_by_receipt':self.invoice_by_receipt,
        })
        if self.type == 'buy':
            receipt_id.write({'line_in_ids': [
                (0, 0, line[0]) for line in receipt_line]})
        else:
            receipt_id.write({'line_out_ids': [
                (0, 0, line[0]) for line in receipt_line]})
        return receipt_id

    @api.one
    def buy_generate_receipt(self):
        '''由购货订单生成采购入库/退货单'''
        receipt_line = []  # 采购入库/退货单行

        for line in self.line_ids:
            # 如果订单部分入库，则点击此按钮时生成剩余数量的入库单
            to_in = line.quantity - line.quantity_in
            if to_in <= 0:
                continue
            if line.goods_id.force_batch_one:
                i = 0
                while i < to_in:
                    i += 1
                    receipt_line.append(
                                self.get_receipt_line(line, single=True))
            else:
                receipt_line.append(self.get_receipt_line(line, single=False))

        if not receipt_line:
            return {}
        receipt_id = self._generate_receipt(receipt_line)
        view_id = (self.type == 'buy'
                   and self.env.ref('buy.buy_receipt_form').id
                   or self.env.ref('buy.buy_return_form').id)
        name = (self.type == 'buy' and u'采购入库单' or u'采购退货单')

        return {
            'name': name,
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': False,
            'views': [(view_id, 'form')],
            'res_model': 'buy.receipt',
            'type': 'ir.actions.act_window',
            'domain': [('id', '=', receipt_id)],
            'target': 'current',
        }


class payment(models.Model):
    _name="payment.plan"
    name=fields.Char(string=u"名称", required=True,
                     help=u'付款计划名称')
    amount_money=fields.Float(string=u"金额", required=True,
                              help=u'付款金额')
    date_application=fields.Date(string=u"申请日期", readonly=True,
                                 help=u'付款申请日期')
    buy_id=fields.Many2one("buy.order",
                           help=u'关联的购货订单')

    @api.one
    def request_payment(self):
        categ = self.env.ref('money.core_category_purchase')
        source_id = self.env['money.invoice'].create({
                            'name': self.buy_id.name,
                            'partner_id': self.buy_id.partner_id.id,
                            'category_id': categ.id, 
                            'date': fields.Date.context_today(self),
                            'amount': self.amount_money,
                            'reconciled': 0,
                            'to_reconcile': self.amount_money,
                            'date_due': fields.Date.context_today(self),
                            'state': 'draft',
                        })
        payment_id = self.env["money.order"].create({
                            'partner_id': self.buy_id.partner_id.id,
                                'date': fields.Date.context_today(self),
                                'source_ids':
                                [(0, 0, {'name':source_id.id, 
                                 'category_id':categ.id, 
                                 'date':source_id.date, 
                                 'amount':self.amount_money, 
                                 'reconciled':0.0, 
                                 'to_reconcile':self.amount_money, 
                                 'this_reconcile':self.amount_money})],
                                'type': 'pay',
                                'amount': self.amount_money,
                                'reconciled': 0,
                                'to_reconcile': self.amount_money,
                                'state': 'draft',
            })   
        self.date_application = datetime.now()


class buy_order_line(models.Model):
    _name = 'buy.order.line'
    _description = u'购货订单明细'

    @api.one
    @api.depends('goods_id')
    def _compute_using_attribute(self):
        '''返回订单行中产品是否使用属性'''
        self.using_attribute = self.goods_id.attribute_ids and True or False

    @api.one
    @api.depends('quantity', 'price_taxed', 'discount_amount', 'tax_rate')
    def _compute_all_amount(self):
        '''当订单行的数量、含税单价、折扣额、税率改变时，改变购货金额、税额、价税合计'''
        self.price = (self.tax_rate != -100
                      and self.price_taxed / (1 + self.tax_rate * 0.01) or 0)
        self.amount = self.quantity * self.price - self.discount_amount  # 折扣后金额
        self.tax_amount = self.amount * self.tax_rate * 0.01  # 税额
        self.subtotal = self.amount + self.tax_amount

    order_id = fields.Many2one('buy.order', u'订单编号', select=True,
                               required=True, ondelete='cascade',
                               help=u'关联订单的编号')
    goods_id = fields.Many2one('goods', u'商品', ondelete='restrict',
                               help=u'商品')
    using_attribute = fields.Boolean(u'使用属性', compute=_compute_using_attribute,
                                     help=u'商品是否使用属性')
    attribute_id = fields.Many2one('attribute', u'属性',
                                   ondelete='restrict',
                                   domain="[('goods_id', '=', goods_id)]",
                                   help=u'商品的属性，当商品有属性时，该字段必输')
    uom_id = fields.Many2one('uom', u'单位', ondelete='restrict',
                             help=u'商品计量单位')
    quantity = fields.Float(u'数量', default=1,
                            digits=dp.get_precision('Quantity'),
                            help=u'下单数量')
    quantity_in = fields.Float(u'已执行数量', copy=False,
                               digits=dp.get_precision('Quantity'),
                               help=u'购货订单产生的入库单/退货单已执行数量')
    price = fields.Float(u'购货单价', compute=_compute_all_amount,
                         store=True, readonly=True,
                         digits=dp.get_precision('Amount'),
                         help=u'不含税单价，由含税单价计算得出')
    price_taxed = fields.Float(u'含税单价',
                               digits=dp.get_precision('Amount'),
                               help=u'含税单价，取自商品成本或对应供应商的购货价')
    discount_rate = fields.Float(u'折扣率%',
                                 help=u'折扣率')
    discount_amount = fields.Float(u'折扣额',
                                   digits=dp.get_precision('Amount'),
                                   help=u'输入折扣率后自动计算得出，也可手动输入折扣额')
    amount = fields.Float(u'金额', compute=_compute_all_amount,
                          store=True, readonly=True,
                          digits=dp.get_precision('Amount'),
                          help=u'金额  = 价税合计  - 税额')
    tax_rate = fields.Float(u'税率(%)',
                            default=lambda self:self.env.user.company_id.import_tax_rate,
                            help=u'默认值取公司进项税率')
    tax_amount = fields.Float(u'税额', compute=_compute_all_amount,
                              store=True, readonly=True,
                              digits=dp.get_precision('Amount'),
                              help=u'由税率计算得出')
    subtotal = fields.Float(u'价税合计', compute=_compute_all_amount,
                            store=True, readonly=True,
                            digits=dp.get_precision('Amount'),
                            help=u'含税单价 乘以 数量')
    note = fields.Char(u'备注',
                       help=u'本行备注')
    # TODO:放到单独模块中 sell_to_buy many2one 到sell.order
    origin = fields.Char(u'销售单号',
                         help=u'以销订购的销售订单号')

    @api.onchange('goods_id', 'quantity')
    def onchange_goods_id(self):
        '''当订单行的产品变化时，带出产品上的单位、成本价。
        在采购订单上选择供应商，自动带出供货价格，没有设置供货价的取成本价格。'''
        if not self.order_id.partner_id:
            raise UserError(u'请先选择一个供应商！')
        if self.goods_id:
            self.uom_id = self.goods_id.uom_id
            if not self.goods_id.cost:
                raise UserError(u'请先设置商品的成本！')
            self.price_taxed = self.goods_id.cost
            for line in self.goods_id.vendor_ids:
                if line.vendor_id == self.order_id.partner_id \
                    and self.quantity >= line.min_qty:
                    self.price_taxed = line.price
                    break

    @api.onchange('quantity', 'price_taxed', 'discount_rate')
    def onchange_discount_rate(self):
        '''当数量、单价或优惠率发生变化时，优惠金额发生变化'''
        price = (self.tax_rate != -100
                 and self.price_taxed / (1 + self.tax_rate * 0.01) or 0)
        self.discount_amount = (self.quantity * price *
                                self.discount_rate * 0.01)

class buy_receipt(models.Model):
    _name = "buy.receipt"
    _inherits = {'wh.move': 'buy_move_id'}
    _inherit = ['mail.thread']
    _description = u"采购入库单"
    _order = 'date desc, id desc'

    @api.one
    @api.depends('line_in_ids.subtotal', 'discount_amount',
                 'payment', 'line_out_ids.subtotal')
    def _compute_all_amount(self):
        '''当优惠金额改变时，改变优惠后金额和本次欠款'''
        total = 0
        if self.line_in_ids:
            # 入库时优惠前总金额
            total = sum(line.subtotal for line in self.line_in_ids)
        elif self.line_out_ids:
            # 退货时优惠前总金额
            total = sum(line.subtotal for line in self.line_out_ids)
        self.amount = total - self.discount_amount
        self.debt = self.amount - self.payment

    @api.one
    @api.depends('is_return', 'invoice_id.reconciled', 'invoice_id.amount')
    def _get_buy_money_state(self):
        '''返回付款状态'''
        if not self.is_return:
            if self.invoice_id.reconciled == 0:
                self.money_state = u'未付款'
            elif self.invoice_id.reconciled < self.invoice_id.amount:
                self.money_state = u'部分付款'
            elif self.invoice_id.reconciled == self.invoice_id.amount:
                self.money_state = u'全部付款'
        # 返回退款状态
        if self.is_return:
            if self.invoice_id.reconciled == 0:
                self.return_state = u'未退款'
            elif abs(self.invoice_id.reconciled) < abs(self.invoice_id.amount):
                self.return_state = u'部分退款'
            elif self.invoice_id.reconciled == self.invoice_id.amount:
                self.return_state = u'全部退款'

    buy_move_id = fields.Many2one('wh.move', u'入库单',
                                  required=True, ondelete='cascade',
                                  help=u'入库单号')
    is_return = fields.Boolean(u'是否退货',
                    default=lambda self: self.env.context.get('is_return'),
                    help=u'是否为退货类型')
    order_id = fields.Many2one('buy.order', u'订单号',
                               copy=False, ondelete='cascade',
                               help=u'产生入库单/退货单的购货订单')
    invoice_id = fields.Many2one('money.invoice', u'发票号', copy=False,
                                 ondelete='set null',
                                 help=u'产生的发票号')
    date_due = fields.Date(u'到期日期', copy=False,
                           help=u'付款截止日期')
    discount_rate = fields.Float(u'优惠率(%)', states=READONLY_STATES,
                                 help=u'整单优惠率')
    discount_amount = fields.Float(u'优惠金额', states=READONLY_STATES,
                                   digits=dp.get_precision('Amount'),
                                   help=u'整单优惠金额，可由优惠率自动计算得出，也可手动输入')
    invoice_by_receipt=fields.Boolean(string=u"按收货结算", default=True,
                                      help=u'如未勾选此项，可在资金行里输入付款金额，订单保存后，采购人员可以单击资金行上的【确认】按钮。')
    amount = fields.Float(u'优惠后金额', compute=_compute_all_amount,
                          store=True, readonly=True,
                          digits=dp.get_precision('Amount'),
                          help=u'总金额减去优惠金额')
    payment = fields.Float(u'本次付款', states=READONLY_STATES,
                           digits=dp.get_precision('Amount'),
                           help=u'本次付款金额')
    bank_account_id = fields.Many2one('bank.account', u'结算账户', 
                                      ondelete='restrict',
                                      help=u'用来核算和监督企业与其他单位或个人之间的债权债务的结算情况')
    debt = fields.Float(u'本次欠款', compute=_compute_all_amount,
                        store=True, readonly=True, copy=False,
                        digits=dp.get_precision('Amount'),
                        help=u'本次欠款金额')
    cost_line_ids = fields.One2many('cost.line', 'buy_id', u'采购费用', copy=False,
                                    help=u'采购费用明细行')
    money_state = fields.Char(u'付款状态', compute=_get_buy_money_state,
                              store=True, default=u'未付款',
                              help=u"采购入库单的付款状态",
                              select=True, copy=False)
    return_state = fields.Char(u'退款状态', compute=_get_buy_money_state,
                               store=True, default=u'未退款',
                               help=u"采购退货单的退款状态",
                               select=True, copy=False)
    modifying = fields.Boolean(u'差错修改中', default=False,
                               help=u'是否处于差错修改中')
    voucher_id = fields.Many2one('voucher', u'入库凭证', readonly=True,
                                 help=u'审核时产生的入库凭证')

    def _compute_total(self, line_ids):
        return sum(line.subtotal for line in line_ids)

    @api.onchange('discount_rate', 'line_in_ids', 'line_out_ids')
    def onchange_discount_rate(self):
        '''当优惠率或订单行发生变化时，单据优惠金额发生变化'''
        line = self.line_in_ids or self.line_out_ids
        total = self._compute_total(line)
        if self.discount_rate:
            self.discount_amount = total * self.discount_rate * 0.01

    def get_move_origin(self, vals):
        return self._name + (self.env.context.get('is_return') and
                             '.return' or '.buy')

    @api.model
    def create(self, vals):
        '''创建采购入库单时生成有序编号'''
        if not self.env.context.get('is_return'):
            name = self._name
        else:
            name = 'buy.return'
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code(name) or '/'

        vals.update({
            'origin': self.get_move_origin(vals)
        })
        return super(buy_receipt, self).create(vals)

    @api.multi
    def unlink(self):
        for receipt in self:
            if receipt.state == 'done':
                raise UserError(u'不能删除已审核的单据')
            move = self.env['wh.move'].search([
                ('id', '=', receipt.buy_move_id.id)
            ])
            move.unlink()

        return super(buy_receipt, self).unlink()

    @api.one
    def _wrong_receipt_done(self):
        if self.state == 'done':
            raise UserError(u'请不要重复审核！')
        batch_one_list_wh = []
        batch_one_list = []
        for line in self.line_in_ids:
            if line.goods_id.force_batch_one:
                wh_move_lines = self.env['wh.move.line'].search([('state', '=', 'done'), ('type', '=', 'in'), ('goods_id', '=', line.goods_id.id)])
                for move_line in wh_move_lines:
                    if (move_line.goods_id.id, move_line.lot) not in batch_one_list_wh and move_line.lot:
                        batch_one_list_wh.append((move_line.goods_id.id, move_line.lot))

            if (line.goods_id.id, line.lot) in batch_one_list_wh:
                raise UserError(u'仓库已存在相同序列号的产品！')

        for line in self.line_in_ids:
            if line.goods_qty <= 0 or line.price_taxed < 0:
                raise UserError(u'产品 %s 的数量和含税单价不能小于0！' % line.goods_id.name)
            if line.goods_id.force_batch_one:
                batch_one_list.append((line.goods_id.id, line.lot))

        if len(batch_one_list) > len(set(batch_one_list)):
            raise UserError(u'不能创建相同序列号的产品！')

        for line in self.line_out_ids:
            if line.goods_qty <= 0 or line.price_taxed < 0:
                raise UserError(u'产品 %s 的数量和含税单价不能小于0！' % line.goods_id.name)
        
        if self.bank_account_id and not self.payment:
            raise UserError(u'结算账户不为空时，需要输入付款额！')
        if not self.bank_account_id and self.payment:
            raise UserError(u'付款额不为空时，请选择结算账户！')
        if self.payment > self.amount:
            raise UserError(u'本次付款金额不能大于折后金额！')
        if (sum(cost_line.amount for cost_line in self.cost_line_ids) != 
            sum(line.share_cost for line in self.line_in_ids)):
            raise UserError(u'采购费用还未分摊或分摊不正确！')
        return

    @api.one
    def _line_qty_write(self):
        if self.order_id:
            line_ids = not self.is_return and self.line_in_ids or self.line_out_ids
            for line in line_ids:
                line.buy_line_id.quantity_in += line.goods_qty

        return

    def _get_invoice_vals(self, category_id, amount, tax_amount):
        '''返回创建 money_invoice 时所需数据'''
        return {
            'move_id': self.buy_move_id.id, 
            'name': self.name,
            'partner_id': self.partner_id.id, 
            'category_id': category_id.id, 
            'date': fields.Date.context_today(self), 
            'amount': amount, 
            'reconciled': 0, 
            'to_reconcile': amount,
            'tax_amount': tax_amount,
            'date_due': self.date_due, 
            'state': 'draft'
        }

    def _receipt_make_invoice(self):
        '''入库单/退货单 生成结算单'''
        if not self.is_return:
            if not self.invoice_by_receipt:
                return False
            amount = self.amount
            tax_amount = sum(line.tax_amount for line in self.line_in_ids)
        else:
            amount = -self.amount
            tax_amount = - sum(line.tax_amount for line in self.line_out_ids)
        categ = self.env.ref('money.core_category_purchase')
        source_id = self.env['money.invoice'].create(
            self._get_invoice_vals(categ, amount, tax_amount)
        )
        self.invoice_id = source_id.id
        return source_id

    @api.one
    def _buy_amount_to_invoice(self):
        '''采购费用产生结算单'''
        if sum(cost_line.amount for cost_line in self.cost_line_ids) > 0:
            for line in self.cost_line_ids:
                cost_id = self.env['money.invoice'].create(
                    self._get_invoice_vals(line.category_id, line.amount, 0)
                )

        return

    @api.one
    def _make_payment(self, source_id):
        if not source_id:
            return False
        if self.payment:
            flag = not self.is_return and 1 or -1
            amount = flag * self.amount
            this_reconcile = flag * self.payment
            categ = self.env.ref('money.core_category_purchase')
            money_lines = [{'bank_id': self.bank_account_id.id, 'amount': this_reconcile}]
            source_lines = [{'name': source_id.id,
                             'category_id': categ.id,
                             'date': source_id.date,
                             'amount': amount,
                             'reconciled': 0.0,
                             'to_reconcile': amount,
                             'this_reconcile': this_reconcile}]
            rec = self.with_context(type='pay')
            money_order = rec.env['money.order'].create({
                    'partner_id': self.partner_id.id,
                    'date': fields.Date.context_today(self),
                    'line_ids':
                    [(0, 0, line) for line in money_lines],
                    'source_ids':
                    [(0, 0, line) for line in source_lines],
                    'type': 'pay',
                    'amount': amount,
                    'reconciled': this_reconcile,
                    'to_reconcile': amount,
                    'state': 'draft'})

    @api.one
    def create_voucher(self):
        '''
        借： 商品分类对应的会计科目 一般是库存商品
        贷：类型为支出的类别对应的会计科目 一般是材料采购

        当一张入库单有多个产品的时候，按对应科目汇总生成多个借方凭证行。

        采购退货单生成的金额为负
        '''
        vouch_id = self.env['voucher'].create({'date': self.date})

        sum = 0
        if not self.is_return:
            for line in self.line_in_ids:
                self.env['voucher.line'].create({
                    'name': self.name,
                    'account_id': line.goods_id.category_id.account_id.id,
                    'debit': line.amount,
                    'voucher_id': vouch_id.id,
                    'goods_id': line.goods_id.id,
                })
                sum += line.amount

            category_expense = self.env.ref('money.core_category_purchase')
            self.env['voucher.line'].create({
                'name': self.name,
                'account_id': category_expense.account_id.id,
                'credit': sum,
                'voucher_id': vouch_id.id,
            })
        if self.is_return:
            for line in self.line_out_ids:
                self.env['voucher.line'].create({
                    'name': self.name,
                    'account_id': line.goods_id.category_id.account_id.id,
                    'debit': -line.amount,
                    'voucher_id': vouch_id.id,
                    'goods_id': line.goods_id.id,
                })
                sum += line.amount

            category_expense = self.env.ref('money.core_category_purchase')
            self.env['voucher.line'].create({
                'name': self.name,
                'account_id': category_expense.account_id.id,
                'credit': -sum,
                'voucher_id': vouch_id.id,
            })

        self.voucher_id = vouch_id
        self.voucher_id.voucher_done()
        return vouch_id

    @api.one
    def buy_receipt_done(self):
        '''审核采购入库单/退货单，更新本单的付款状态/退款状态，并生成结算单和付款单'''
        #报错
        self._wrong_receipt_done()

        #将收货/退货数量写入订单行
        self._line_qty_write()

        # 创建入库的会计凭证
        self.create_voucher()

        # 入库单/退货单 生成结算单
        source_id = self._receipt_make_invoice()
        # 采购费用产生结算单
        self._buy_amount_to_invoice()
        # 生成付款单
        self._make_payment(source_id)
        # 调用wh.move中审核方法，更新审核人和审核状态
        self.buy_move_id.approve_order()
        # 生成分拆单 FIXME:无法跳转到新生成的分单
        if self.order_id and not self.modifying:
            return self.order_id.buy_generate_receipt()

    @api.one
    def buy_receipt_draft(self):
        '''反审核采购入库单/退货单，更新本单的付款状态/退款状态，并删除生成的结算单、付款单及凭证'''
        # 查找产生的付款单
        source_line = self.env['source.order.line'].search(
                [('name', '=', self.invoice_id.id)])
        for line in source_line:
            line.money_id.money_order_draft()
            line.money_id.unlink()
        # 查找产生的结算单
        invoice_ids = self.env['money.invoice'].search(
                [('name', '=', self.invoice_id.name)])
        for invoice in invoice_ids:
            invoice.money_invoice_draft()
            invoice.unlink()
        # 如果存在分单，则将差错修改中置为 True，再次审核时不生成分单
        self.modifying = False
        receipt_ids = self.search(
            [('order_id', '=', self.order_id.id)])
        if len(receipt_ids) > 1:
            self.modifying = True
        # 将订单行中已执行数量清零
        order = self.env['buy.order'].search(
            [('id', '=', self.order_id.id)])
        for line in order.line_ids:
            line.quantity_in = 0
        # 调用wh.move中反审核方法，更新审核人和审核状态
        self.buy_move_id.cancel_approved_order()

        # 反审核采购入库单时删除对应的入库凭证
        if self.voucher_id:
            if self.voucher_id.state == 'done':
                self.voucher_id.voucher_draft()
            self.voucher_id.unlink()

    @api.one
    def buy_share_cost(self):
        '''入库单上的采购费用分摊到入库单明细行上'''
        total_amount = 0
        for line in self.line_in_ids:
            total_amount += line.amount
        for line in self.line_in_ids:
            cost = sum(cost_line.amount for cost_line in self.cost_line_ids)
            line.share_cost = cost / total_amount * line.amount
        return True


class wh_move_line(models.Model):
    _inherit = 'wh.move.line'
    _description = u"采购入库明细"

    buy_line_id = fields.Many2one('buy.order.line',
                                  u'购货单行', ondelete='cascade',
                                  help=u'对应的购货订单行')
    share_cost = fields.Float(u'采购费用',
                              digits=dp.get_precision('Amount'),
                              help=u'点击分摊按钮或审核时将采购费用进行分摊得出的费用')

    @api.multi
    @api.onchange('goods_id', 'tax_rate')
    def onchange_goods_id(self):
        '''当订单行的产品变化时，带出产品上的成本价，以及公司的进项税'''
        if self.goods_id:
            if not self.goods_id.cost:
                raise UserError(u'请先设置商品的成本！')

            is_return = self.env.context.get('default_is_return')
            # 如果是采购入库单行 或 采购退货单行
            if (self.type == 'in' and not is_return) or (self.type == 'out' and is_return):
                self.tax_rate = self.env.user.company_id.import_tax_rate
                self.price_taxed = self.goods_id.cost

        return super(wh_move_line,self).onchange_goods_id()


class cost_line(models.Model):
    _inherit = 'cost.line'

    buy_id = fields.Many2one('buy.receipt', u'入库单号', ondelete='cascade',
                             help=u'与采购费用关联的入库单号')


class money_invoice(models.Model):
    _inherit = 'money.invoice'

    move_id = fields.Many2one('wh.move', string=u'出入库单',
                              readonly=True, ondelete='cascade',
                              help=u'生成此发票的出入库单号')


class money_order(models.Model):
    _inherit = 'money.order'

    @api.multi
    def money_order_done(self):
        ''' 将已核销金额写回到购货订单中的已执行金额 '''
        res = super(money_order, self).money_order_done()
        move = False
        for source in self.source_ids:
            if self.type == 'pay':
                move = self.env['buy.receipt'].search(
                    [('invoice_id', '=', source.name.id)])
                if move.order_id:
                    move.order_id.amount_executed = abs(source.name.reconciled)
        return res

    @api.multi
    def money_order_draft(self):
        ''' 将购货订单中的已执行金额清零'''
        res = super(money_order, self).money_order_draft()
        move = False
        for source in self.source_ids:
            if self.type == 'pay':
                move = self.env['buy.receipt'].search(
                    [('invoice_id', '=', source.name.id)])
                if move.order_id:
                    move.order_id.amount_executed = 0
        return res


class buy_adjust(models.Model):
    _name = "buy.adjust"
    _inherit = ['mail.thread']
    _description = u"采购调整单"
    _order = 'date desc, id desc'

    name = fields.Char(u'单据编号', copy=False,
                       help=u'调整单编号，保存时可自动生成')
    order_id = fields.Many2one('buy.order', u'原始单据', states=READONLY_STATES,
                             copy=False, ondelete='restrict',
                             help=u'要调整的原始购货订单')
    date = fields.Date(u'单据日期', states=READONLY_STATES,
                       default=lambda self: fields.Date.context_today(self),
                       select=True, copy=False,
                       help=u'调整单创建日期，默认是当前日期')
    line_ids = fields.One2many('buy.adjust.line', 'order_id', u'调整单行',
                               states=READONLY_STATES, copy=True,
                               help=u'调整单明细行，不允许为空')
    approve_uid = fields.Many2one('res.users', u'审核人',
                            copy=False, ondelete='restrict',
                            help=u'审核调整单的人')
    state = fields.Selection(BUY_ORDER_STATES, u'审核状态',
                             select=True, copy=False,
                             default='draft',
                             help=u'调整单审核状态')
    note = fields.Text(u'备注',
                       help=u'单据备注')

    @api.multi
    def unlink(self):
        for order in self:
            if order.state == 'done':
                raise UserError(u'不能删除已审核的单据')

        return super(buy_adjust, self).unlink()

    @api.one
    def buy_adjust_done(self):
        '''审核采购调整单：
        当调整后数量 < 原单据中已入库数量，则报错；
        当调整后数量 > 原单据中已入库数量，则更新原单据及入库单分单的数量；
        当调整后数量 = 原单据中已入库数量，则更新原单据数量，删除入库单分单；
        当新增产品时，则更新原单据及入库单分单明细行。
        '''
        if self.state == 'done':
            raise UserError(u'请不要重复审核！')
        if not self.line_ids:
            raise UserError(u'请输入产品明细行！')
        for line in self.line_ids:
            if  line.price_taxed < 0:
                raise UserError(u'产品含税单价不能小于0！')
        buy_receipt = self.env['buy.receipt'].search(
                    [('order_id', '=', self.order_id.id),
                     ('state', '=', 'draft')])
        if not buy_receipt:
            raise UserError(u'采购入库单已全部入库，不能调整')
        for line in self.line_ids:
            origin_line = self.env['buy.order.line'].search(
                        [('goods_id', '=', line.goods_id.id),
                         ('attribute_id', '=', line.attribute_id.id),
                         ('order_id', '=', self.order_id.id)])
            if len(origin_line) > 1:
                raise UserError(u'要调整的商品%s在原始单据中不唯一' % line.goods_id.name)
            if origin_line:
                origin_line.quantity += line.quantity # 调整后数量
                origin_line.note = line.note
                if origin_line.quantity < origin_line.quantity_in:
                    raise UserError(u'%s调整后数量不能小于原订单已入库数量' % line.goods_id.name)
                elif origin_line.quantity > origin_line.quantity_in:
                    # 查找出原购货订单产生的草稿状态的入库单明细行，并更新它
                    move_line = self.env['wh.move.line'].search(
                                    [('buy_line_id', '=', origin_line.id),
                                     ('state', '=', 'draft')])
                    if move_line:
                        move_line.goods_qty += line.quantity
                        move_line.goods_uos_qty = move_line.goods_qty / move_line.goods_id.conversion
                        move_line.note = line.note
                    else:
                        raise UserError(u'商品%s已全部入库，建议新建购货订单' % line.goods_id.name)
                # 调整后数量与已入库数量相等时，删除产生的入库单分单
                else:
                    buy_receipt.unlink()
            else:
                vals = {
                    'order_id': self.order_id.id,
                    'goods_id': line.goods_id.id,
                    'attribute_id': line.attribute_id.id,
                    'quantity': line.quantity,
                    'uom_id': line.uom_id.id,
                    'price_taxed': line.price_taxed,
                    'discount_rate': line.discount_rate,
                    'discount_amount': line.discount_amount,
                    'tax_rate': line.tax_rate,
                    'note': line.note or '',
                }
                new_line = self.env['buy.order.line'].create(vals)
                receipt_line = []
                if line.goods_id.force_batch_one:
                    i = 0
                    while i < line.quantity:
                        i += 1
                        receipt_line.append(
                                    self.order_id.get_receipt_line(new_line, single=True))
                else:
                    receipt_line.append(self.order_id.get_receipt_line(new_line, single=False))
                buy_receipt.write({'line_in_ids': [(0, 0, li[0]) for li in receipt_line]})
        self.state = 'done'
        self.approve_uid = self._uid


class buy_adjust_line(models.Model):
    _name = 'buy.adjust.line'
    _description = u'采购调整单明细'

    @api.one
    @api.depends('goods_id')
    def _compute_using_attribute(self):
        '''返回订单行中产品是否使用属性'''
        self.using_attribute = self.goods_id.attribute_ids and True or False

    @api.one
    @api.depends('quantity', 'price_taxed', 'discount_amount', 'tax_rate')
    def _compute_all_amount(self):
        '''当订单行的数量、单价、折扣额、税率改变时，改变购货金额、税额、价税合计'''
        self.price = self.price_taxed / (1 + self.tax_rate * 0.01)
        self.amount = self.quantity * self.price - self.discount_amount  # 折扣后金额
        self.tax_amount = self.amount * self.tax_rate * 0.01  # 税额
        self.subtotal = self.amount + self.tax_amount

    order_id = fields.Many2one('buy.adjust', u'订单编号', select=True,
                               required=True, ondelete='cascade',
                               help=u'关联的调整单编号')
    goods_id = fields.Many2one('goods', u'商品', ondelete='restrict',
                               help=u'商品')
    using_attribute = fields.Boolean(u'使用属性', compute=_compute_using_attribute,
                                     help=u'商品是否使用属性')
    attribute_id = fields.Many2one('attribute', u'属性',
                                   ondelete='restrict',
                                   domain="[('goods_id', '=', goods_id)]",
                                   help=u'商品的属性，当商品有属性时，该字段必输')
    uom_id = fields.Many2one('uom', u'单位', ondelete='restrict',
                             help=u'商品计量单位')
    quantity = fields.Float(u'调整数量', default=1,
                            digits=dp.get_precision('Quantity'),
                            help=u'相对于原单据对应明细行的调整数量，可正可负')
    price = fields.Float(u'购货单价', compute=_compute_all_amount,
                         store=True, readonly=True,
                         digits=dp.get_precision('Amount'),
                         help=u'不含税单价，由含税单价计算得出')
    price_taxed = fields.Float(u'含税单价',
                               digits=dp.get_precision('Amount'),
                               help=u'含税单价，取自商品成本')
    discount_rate = fields.Float(u'折扣率%',
                                 help=u'折扣率')
    discount_amount = fields.Float(u'折扣额',
                                   digits=dp.get_precision('Amount'),
                                   help=u'输入折扣率后自动计算得出，也可手动输入折扣额')
    amount = fields.Float(u'金额', compute=_compute_all_amount,
                          store=True, readonly=True,
                          digits=dp.get_precision('Amount'),
                          help=u'金额  = 价税合计  - 税额')
    tax_rate = fields.Float(u'税率(%)', default=lambda self:self.env.user.company_id.import_tax_rate,
                            help=u'默认值取公司进项税率')
    tax_amount = fields.Float(u'税额', compute=_compute_all_amount,
                              store=True, readonly=True,
                              digits=dp.get_precision('Amount'),
                              help=u'由税率计算得出')
    subtotal = fields.Float(u'价税合计', compute=_compute_all_amount,
                            store=True, readonly=True,
                            digits=dp.get_precision('Amount'),
                            help=u'含税单价 乘以 数量')
    note = fields.Char(u'备注',
                       help=u'本行备注')

    @api.onchange('goods_id')
    def onchange_goods_id(self):
        '''当订单行的产品变化时，带出产品上的单位、默认仓库、成本价'''
        if self.goods_id:
            self.uom_id = self.goods_id.uom_id
            if not self.goods_id.cost:
                raise UserError(u'请先设置商品的成本！')
            self.price_taxed = self.goods_id.cost

    @api.onchange('quantity', 'price_taxed', 'discount_rate')
    def onchange_discount_rate(self):
        '''当数量、单价或优惠率发生变化时，优惠金额发生变化'''
        price = self.price_taxed / (1 + self.tax_rate * 0.01)
        self.discount_amount = (self.quantity * price *
                                self.discount_rate * 0.01)
