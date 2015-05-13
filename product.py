from trytond.model import fields
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval

__metaclass__ = PoolMeta

__all__ = ['Account', 'Product', 'TimesheetWork', 'Template',
    'ProductKitLine']


class Account:
    __name__ = 'analytic_account.account'

    works = fields.One2Many('timesheet.work', 'account', 'Work')

    full_name = fields.Function(fields.Char('Full Name'),
        'get_full_name')

    def get_full_name(self, name):
        if self.parent:
            return self.parent.get_full_name(name) + '\\' + self.name
        else:
            return self.name


class ProductKitLine:
    __name__ = 'product.kit.line'

    @classmethod
    def __setup__(cls):
        super(ProductKitLine, cls).__setup__()
        cls._error_messages.update({
            'line_with_work': ('You cannot modify componet  "%s" associated'
                ' to works'),
                })

    @classmethod
    def create(cls, vlist):
        product_kit_lines = super(ProductKitLine, cls).create(vlist)
        for pkl in product_kit_lines:
            pkl.product.create_work()
        return product_kit_lines

    @classmethod
    def delete(cls, lines):
        works_to_delete = []
        for line in lines:
            for work in line.product.works:
                work.check_delete()
                works_to_delete.append(work)
        TimesheetWork = Pool().get('timesheet.work')
        TimesheetWork.delete(works_to_delete)
        super(ProductKitLine, cls).delete(lines)

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        args = []
        for records, values in zip(actions, actions):
            if values.get('product'):
                for record in records:
                    if record.product.works:
                        cls.raise_user_error('line_with_work', record.rec_name)
            args.extend((records, values))
        super(ProductKitLine, cls).write(*args)


class Template:
    __name__ = 'product.template'

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        args, create_works = [], []
        for records, values in zip(actions, actions):
            print [f[:17] for f in values.keys()]
            if (values.get('type', '') == 'service' or
                    any(f[:17] == 'analytic_account_' for f in values.keys())):
                create_works.extend(records)
            args.extend((records, values))
        super(Template, cls).write(*args)
        print create_works
        for template in create_works:
            for product in template.products:
                product.create_work()

    @classmethod
    def validate(cls, templates):
        super(Template, cls).validate(templates)
        for template in templates:
            for product in template.products:
                product.check_work_product_consistance()


class Product:
    __name__ = 'product.product'

    works = fields.One2Many('timesheet.work', 'product', 'Works')
    kit_component = fields.Function(fields.Boolean('Kit Component'),
        'get_kit_component')

    @classmethod
    def __setup__(cls):
        super(Product, cls).__setup__()
        cls._error_messages.update({
            'product_work_consistance': ('You can not modify  "%s" product '
                'fields: "Type, Kit components or Analytic Accounts" '
                'because exists Timesheet Work associated'),
                })

    def get_kit_component(self, name=True):
        PKL = Pool().get('product.kit.line')
        kits = PKL.search([('product', '=', self.id)], limit=1)
        if kits:
            return True
        return False

    def check_create_work(self):
        if (self.kit_component and self.analytic_accounts and
                self.type == 'service'):
            return True
        return False

    def create_work(self):
        if not self.check_create_work():
            return
        values = self.get_work_values()
        Work = Pool().get('timesheet.work')
        return Work.create(values)

    def get_work_values(self):
        values = []
        for account in self.analytic_accounts.accounts:
            value = {
                'name': account.full_name + '\\' + self.name,
                'timesheet_available': True,
                'company': Transaction().context.get('company'),
                'product': self.id,
                'account': account.id,
            }
            values.append(value)
        return values

    def check_work_product_consistance(self):
        if not self.works or (self.works and self.check_create_work()):
            return True
        self.raise_user_error('product_work_consistance', self.rec_name)

    @classmethod
    def validate(cls, products):
        super(Product, cls).validate(products)
        for product in products:
            product.check_work_product_consistance()


class TimesheetWork:
    __name__ = 'timesheet.work'

    product = fields.Many2One('product.product', 'Product')

    def get_rec_name(self, name):
        if not (self.product and self.account):
            return self.name
        return self.account.full_name + '\\' + self.product.rec_name

    def check_delete(self):
        if self.product and self.timesheet_lines:
            self.raise_user_error('work_with_lines', self.rec_name)
        return True

    @classmethod
    def __setup__(cls):
        super(TimesheetWork, cls).__setup__()
        readonly = Eval('product')
        previous_readonly = cls.name.states.get('readonly')
        if previous_readonly:
            readonly = readonly | previous_readonly
        cls.name.states.update({
            'invisible': readonly,
            })

        cls._error_messages.update({
            'work_with_lines': ('You cannot delete work  "%s" with '
                'lines computed '),
                })
