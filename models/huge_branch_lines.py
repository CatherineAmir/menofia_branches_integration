from odoo import fields, models, api,_
from datetime import datetime
import logging
import cx_Oracle
from datetime import datetime, date
import datetime as dt
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError, ValidationError, AccessError
import json

_logger = logging.getLogger(__name__)

class InvSummaryBranch(models.Model):
    _inherit = 'sita.inv_summary'

    branch_id=fields.Many2one('consumption.branch',string="Branch Name")
    branch_code=fields.Char(related='branch_id.code',store=1)

    @api.model
    def init(self):
        self.env.cr.execute("""

                      DROP FUNCTION IF EXISTS batch_create_summary (TEXT);
                      CREATE or REPLACE FUNCTION batch_create_summary(data TEXT)
                      RETURNS VOID AS $BODY$
                      DECLARE

                      records TEXT[];
                      inv_rec TEXT[];
                      rec TEXT;
                      move_exist integer;
                      v_inv_no TEXT;
                      my_state TEXT;
                      my_date integer;
                      cust_name TEXT;
                      create_date timestamp without time zone;

                      activated BOOL;
                      branch_name int;
                      branch_code text;


                      BEGIN
                          SELECT string_to_array(data,'|')INTO records;
                          foreach rec in ARRAy records LOOP
                              SELECT String_to_array(rec,'~~') INTO inv_rec;
                              v_inv_no=inv_rec[1];
                              my_state=inv_rec[2];
                              my_date=(select id from sita_inv_huge_import where name=(SELECT TO_DATE(inv_rec[3],'YYYY-MM-DD') order by id desc limit 1)order by id desc limit 1);
                              create_date=inv_rec[4];
                              activated=inv_rec[5];
                              cust_name=inv_rec[6];
                              branch_name=inv_rec[7];
                              branch_code=inv_rec[8];




                          select id from sita_inv_summary where name=v_inv_no into move_exist ;
                          if move_exist is NULL THEN
                              insert into sita_inv_summary(name,state,import_id,invoice_date,active,customer_name,error,branch_id,branch_code)

                                                   values(v_inv_no,my_state,my_date,create_date,activated,cust_name,null,branch_name,branch_code);
                          else 
                           update sita_inv_summary 
                           set error = NULL,
                           customer_name=cust_name

                           where name=v_inv_no;


                          END IF;


                          END LOOP;
                      END;

                      $BODY$
                      LANGUAGE plpgsql;

                              """)


class HugeImportBranchlines(models.Model):
    _name = 'import_branch_lines'
    _description = 'branch_lines'

    import_id = fields.Many2one('sita_inv.huge_import',auto_join=1)
    branch_id=fields.Many2one('consumption.branch',required=1)
    branch_code=fields.Char(related='branch_id.code')
    total_invoices = fields.Integer('Total Invoices', compute="_compute_numbers", store=True)
    total_posted = fields.Integer('Total Imported Invoice', compute="_compute_numbers", store=True)
    total_not_imported = fields.Integer('Total Not imported', compute="_compute_numbers", store=True)

    state = fields.Selection(selection=[('not_imported', 'Not Imported'),
                                        ('partially_imported', 'Partially Imported'),
                                        ('completely_imported', 'Completely Imported')], default='not_imported',
                             copy=False)

    @api.depends('import_id.summary_ids_posted', 'import_id.summary_ids_not_imported')
    def _compute_numbers(self):
        for r in self:
            r.total_not_imported = len(r.import_id.summary_ids_not_imported.filtered(lambda x:x.branch_id.id==r.branch_id.id))
            r.total_posted = len(r.import_id.summary_ids_posted.filtered(lambda x:x.branch_id.id==r.branch_id.id))
            r.total_invoices = r.total_posted + r.total_not_imported
            r.adjust_state()

    def adjust_state(self):
        if self.total_invoices == 0:
            self.state = 'not_imported'
        else:
            if self.total_invoices == self.total_posted:
                self.state = 'completely_imported'
            elif self.total_invoices == self.total_not_imported:
                self.state = 'not_imported'
            else:
                self.state = 'partially_imported'




    def action_import_branch(self):
        self.import_id.first_import(branch_id=self.branch_id)
        self.adjust_state()
        self._compute_numbers()
        pass

    def action_import_rest(self):
        self.import_id.partially_import(branch_id=self.branch_id)
        self.adjust_state()
        self._compute_numbers()
        
        pass



class HugeImportBranches(models.Model):
    _inherit='sita_inv.huge_import'

    branch_line_ids=fields.One2many('import_branch_lines','import_id')

    @api.model
    def create(self,vals):
        res=super(HugeImportBranches,self).create(vals)
        res.create_branch_lines()
        return res

    def create_branch_lines(self):
        branches=self.env['consumption.branch'].sudo().search([])

        if branches:
            self.env['import_branch_lines'].create([{
                'import_id':self.id,
                'branch_id':b.id

            } for b in branches])

    def first_import(self,branch_id=None):
        self.message_post(body="Start importing")

        data_to_test = self.connect_database(self.database_set, self.name, [], [],branch_id=branch_id.code)

        self.error_dict.clear()
        self.create_summary(data_to_test['INVOICE ID'], data_to_test['Customer Name'],branch_id=branch_id)
        self.test_all(data_to_test)


    def partially_import(self, not_imported=None,branch_id=None):
        self.message_post(body="Continue importing importing with branch_id {}".format(branch_id.code))
        imported = self.cal_imported()

        names = []
        if not not_imported:
            not_imported = self.summary_ids_not_imported
        for n in not_imported:
            names.append(str(n.name))
        # _logger.info('domain_names %s', names)
        data_to_test = self.connect_database(self.database_set, self.name, names, imported,branch_id=branch_id.code)
        # logger.info('data_to_test %s',json.dumps(data_to_test))
        self.error_dict.clear()
        self.create_summary(data_to_test['INVOICE ID'], data_to_test['Customer Name'],branch_id=branch_id.id)

        self.test_all(data_to_test)



    def connect_database(self, dataset, my_date, domain, imported,branch_id=None):
        # _logger.info('domain %s', domain)
        if not branch_id:
            _logger.info("in the if not branch")
            data_to_test=super(HugeImportBranches,self).connect_database(dataset, my_date, domain, imported)
            return data_to_test


        ip = '192.168.40.6'
        # _logger.info('in the inherited connect')

        port = 1521
        SID = 'orcl'
        try:
            cx_Oracle.init_oracle_client(lib_dir=r"D:\instantclient_21_3")
        except Exception as e:
            # _logger.info('error %s',e)
            pass

        try:
            dsn_tns = cx_Oracle.makedsn(ip, port, service_name=SID)
        except Exception as e:
            raise AccessError(_("Can't Connect to Oracle DB %s", e))

        username = 'mnftax'
        password = 'mnftax'
        try:
            conn = cx_Oracle.connect(username, password, dsn_tns)

        except  Exception as e:
            raise AccessError(_("Cann't login into the Oracle database %s", e))

        if dataset == 'consumption':

            if self.invoice_type == 'invoice':
                if self.special_customer:

                    view_name = "BILLELEC_TAXD"
                else:

                    view_name = "BILLELEC_TAX"

                query = """
                              select INVOICE_ID,
                              INVOICE_TYPE,
                              RELATED_INVOICE,
                              CUSTOMER_NAME,
                              COMPANY_PERSON,
                              COUNTRY_CODE,
                              STATE,
                              CITY,
                              STREET,
                              BUILDING_NO,
                              NATIONAL_ID,
                              PASSPORT_ID,
                              TAX_ID,
                              BRANCH_CODE,
                              ACTIVITY_CODE,
                              DATE_ISSUE,
                              TIMME_ISSUED,
                              INVOICE_DISCOUNT,
                              PRODUCT_CODE,
                              '',
                              QUANTITY,
                              UNIT,
                              CUSTOMER_CURRENCY,
                              EXCHANGE_RATE,
                              PRICE,
                              DISCOUNT,
                              TAX_CODE,
                              '',
                              ''
                              
                              from {view:}
                              where 
                                COMPCODE=:branch_code
                                and 
                              to_date(date_issue, 'dd/mm/rrrr') = to_date(:mydate, 'dd/mm/rrrr')

                           """.format(view=view_name)
                            # COMPCODE=:branch_code
                             
                              
                              # and 
                           
                # query = """
                              # select *
                              # from {view:}
                              # WHERE ROWNUM <= 5
                              
                           # """.format(view=view_name)
                           # where
                              # to_date(date_issue, 'dd/mm/rrrr') = to_date(:mydate, 'dd/mm/rrrr')
                              # limit 3
                _logger.info('ready to connect consumption invoice %s',branch_id)

                cursor = conn.cursor()
                # _logger.info("Query %s", query)
                cursor.execute(query, mydate=str(my_date.strftime('%d/%m/%Y')),branch_code=branch_id)
                # 
                # cursor.execute(query,)
                res = cursor.fetchall()
                _logger.info('res %s',json.dumps(res))
                

                columns = cursor.description
                _logger.info('len res consumption description %s', columns)
            else:
                query_1 = """

                  select INVOICE_ID,
                  INVOICE_TYPE,
                  RELATED_INVOICE,
                  CUSTOMER_NAME,
                  COMPANY_PERSON,
                  COUNTRY_CODE,
                  STATE,
                  CITY,
                  STREET,
                  BUILDING_NO,
                  NATIONAL_ID,
                  PASSPORT_ID,
                  TAX_ID,
                  BRANCH_CODE,
                  ACTIVITY_CODE,
                  DATE_ISSUE,
                  TIMME_ISSUED,
                  INVOICE_DISCOUNT,
                  PRODUCT_CODE,
                  '',
                  QUANTITY,
                  UNIT,
                  CUSTOMER_CURRENCY,
                  EXCHANGE_RATE,
                  PRICE,
                  DISCOUNT,
                  TAX_CODE,
                  '',
                  ''
                  from billelec_tax_discount 
                  where


                   to_date(date_issue, 'dd/mm/rrrr') >= to_date(:mydate, 'dd/mm/rrrr') and
                    to_date(date_issue, 'dd/mm/rrrr') <= to_date(:mydate2, 'dd/mm/rrrr')
                   
                   
                                   """


                query_2 = """

                                  select INVOICE_ID,
                                  INVOICE_TYPE,
                                  RELATED_INVOICE,
                                  CUSTOMER_NAME,
                                  COMPANY_PERSON,
                                  COUNTRY_CODE,
                                  STATE,
                                  CITY,
                                  STREET,
                                  BUILDING_NO,
                                  NATIONAL_ID,
                                  PASSPORT_ID,
                                  TAX_ID,
                                  BRANCH_CODE,
                                  ACTIVITY_CODE,
                                  DATE_ISSUE,
                                  TIMME_ISSUED,
                                  INVOICE_DISCOUNT,
                                  PRODUCT_CODE,
                                  '',
                                  QUANTITY,
                                  UNIT,
                                  CUSTOMER_CURRENCY,
                                  EXCHANGE_RATE,
                                  PRICE,
                                  DISCOUNT,
                                  TAX_CODE,
                                  '',
                                  ''
                                  from billelec_tax_add 
                                  where

                                to_date(date_issue, 'dd/mm/rrrr') >= to_date(:mydate, 'dd/mm/rrrr') and
                                to_date(date_issue, 'dd/mm/rrrr') <= to_date(:mydate2, 'dd/mm/rrrr') and
                                 
                               
                                   """

                # _logger.info('ready to connect discount')
                # _logger.info('my date %s', str(my_date.strftime('%d/%m/%Y')))

                cursor = conn.cursor()
                cursor.execute(query_1, mydate=str(my_date.strftime('%d/%m/%Y')),
                               mydate2=str((my_date + relativedelta(day=31)).strftime('%d/%m/%Y')))
                res_1 = cursor.fetchall()
                cursor.execute(query_2, mydate=str(my_date.strftime('%d/%m/%Y')),
                               mydate2=str((my_date + relativedelta(day=31)).strftime('%d/%m/%Y')))

                res_2 = cursor.fetchall()

                _logger.info('Connection Done')

                res = res_1 + res_2

                # _logger.info('res %s',json.dumps(res))
                # _logger.info('len res %s', len(res))

            columns = cursor.description
        else:
            ip = '192.168.40.6'

            if not ip:
                raise ValidationError(_('There is No  IP address to connect'))


            else:
                port = 1521
                SID = 'orcl'
                try:
                    cx_Oracle.init_oracle_client(lib_dir=r"C:\instantclient_21_3")
                except Exception as e:
                    # _logger.info('error %s',e)
                    pass

                try:
                    dsn_tns = cx_Oracle.makedsn(ip, port, service_name=SID)
                except Exception as e:
                    raise AccessError(_("Can't Connect to Oracle DB %s", e))

                username = 'mnftax'
                password = 'mnftax'
                try:
                    conn = cx_Oracle.connect(username, password, dsn_tns)
                # print(conn.version)
                except  Exception as e:
                    raise AccessError(_("Cann't login into the Oracle database %s", e))

                if dataset == 'customer_service':
                    view_name = 'CSELEC_TAX'
                else:
                    view_name = 'CSELEC_TAX_CRPS'

                query = """select INVOICE_ID,
                   INVOICE_TYPE,
                   RELATED_INVOICE,
                   CUSTOMER_NAME,
                   COMPANY_PERSON,
                   COUNTRY_CODE,
                   STATE,
                   CITY,
                   STREET,
                   BUILDING_NO,
                   NATIONAL_ID,
                   PASSPORT_ID,
                   TAX_ID,
                   BRANCH_CODE,
                   ACTIVITY_CODE,
                   DATE_ISSUE,
                   TIMME_ISSUED,
                   INVOICE_DISCOUNT,
                   PRODUCT_CODE,
                   '',
                   QUANTITY,
                   UNIT,
                   CUSTOMER_CURRENCY,
                   EXCHANGE_RATE,
                   PRICE,
                   DISCOUNT,
                   TAX_CODE,
                   '',
                   ''


                   from {view:}

                   where   
                   to_date(date_issue,'dd/mm/rrrr')= to_date(:mydate,'dd/mm/rrrr')""".format(view=view_name)
                _logger.info('ready to connect')

                cursor = conn.cursor()
                # try:
                cursor.execute(query, mydate=str(my_date.strftime('%d/%m/%Y')))
                _logger.info('Connection Done')

                res = cursor.fetchall()
                # _logger.info('res %s',json.dumps(res))
                # _logger.info('len res %s', len(res))
                self.total_number_of_invoices=len(list(set(res[i][0] for i in range(len(res)))))
                _logger.info('res invoice names %s',self.total_number_of_invoices)
                self.total_number_of_lines=len(res)
                self.env.cr.commit()
                self.env.cr.savepoint()

                columns = cursor.description
            # conn.close()
        # _logger.info('ROWS %s', res[0])

        first_row = ['INVOICE ID', 'Invoice Type', 'Related Invoice', 'Customer Name', 'company person',
                     'Country Code',
                     'State', 'City', 'Street', 'Building Number', 'National ID', 'Passport ID', 'Tax ID',
                     'Branch Code',
                     'Activity Code', 'Date Issued', 'Time Issued', 'Invoice Discount(fixed)', 'Product Code',
                     'Product Desc', 'Quantity',
                     'Unit', 'Customer Currency', 'Exchange Rate', 'Customer Price', 'Discount(%)(line)',
                     'Taxes Codes', 'Value Difference', 'Fixed Discount After Tax']

        self.data.clear()
        product_taxes = {'EG-266662870-1527': 'OF04', 'EG-266662870-854': 'OF02'}
        taxes_mapped = []

        for row in range(0, len(res)):
            if domain:
                if str(res[row][0]) not in domain or str(res[row][0]) in imported:
                    # if len(domain):
                    # _logger.info('res[row][0] not in domain %s', res[row][0])
                    continue

            if str(res[row][18]) in product_taxes.keys():
                p_dict = {'Invoice ID': str(res[row][0]), 'Fixed Tax': product_taxes[res[row][18]],
                          'Fixed Tax Amount': res[row][24]}
                # print('p_dict',p_dict)
                taxes_mapped.append(p_dict)
                continue
            elm = {}
            for col in range(0, len(res[row])):

                if col == 0:
                    if str(res[row][0]) in imported:
                        _logger.info('in imported')
                        continue

                    elm[first_row[col]] = str(res[row][col])
                    # _logger.info('invoice_id %s', str(res[row][col]))


                elif str(first_row[col]) == 'Branch Code':
                    elm[first_row[col]] = 0


                elif first_row[col] == 'Date Issued':
                    elm[first_row[col]] = datetime.strptime(res[row][col], '%d/%m/%Y').strftime('%d-%m-%Y')
                    # _logger.info('date _issued %s', datetime.strptime(res[row][col], '%d/%m/%Y').strftime('%d-%m-%Y'))



                else:

                    elm[first_row[col]] = res[row][col] or ''
            if str(res[row][0]) not in imported:
                # _logger.info('added element in data')
                elm['Fixed Tax'] = ''
                elm['Fixed Tax Amount'] = ''
                self.data.append(elm)
            # print('taxes_mapped',taxes_mapped)

        self.add_tax_to_data(taxes_mapped)

        # print('data',data)

        data_to_test = {}
        for col in range(0, len(first_row)):

            getted_rows = []

            for row in range(0, len(res)):
                if domain:
                    if str(res[row][0]) not in domain or str(res[row][0]) in imported:
                        continue
                if col == 0:
                    # _logger.info('str(res[row][col] %s',str(res[row][col]))
                    getted_rows.append(str(res[row][col]))

                elif first_row[col] == 'Branch Code':
                    getted_rows.append(0)
                elif first_row[col] == 'Date Issued':
                    getted_rows.append(datetime.strptime(res[row][col], '%d/%m/%Y').strftime('%d-%m-%Y'))
                else:

                    getted_rows.append(res[row][col] or '')

            data_to_test[first_row[col]] = getted_rows
        # _logger.info('data_to_tested %s', data_to_test)
        # _logger.info('dataa %s',json.dumps(self.data))
        # _logger.info('domain %s', domain)
        # _logger.info('data %s', self.data)

        conn.close()
        # _logger.info('data ready to test len data %s', len(self.data))
        return data_to_test

    def create_summary(self, inv_names, inv_cust,branch_id=None):

        inv_cust = list(set(inv_cust))
        # _logger.info('len inv_cust %s',len(list(set(inv_cust))))
        # _logger.info('len inv_names %s',len(list(set(inv_names))))
        all_summary = []

        for i in self.data:
            one_summary = []
            one_summary.append(str(i['INVOICE ID']).split('.')[0])

            one_summary.append('not_imported')

            one_summary.append(str(self.name).split('.')[0])
            one_summary.append(str(self.sheet_date))
            one_summary.append('True')
            one_summary.append(str(i['Customer Name']))
            if branch_id:
                one_summary.append(str(branch_id.id))
                one_summary.append(str(branch_id.code))
            else:
                one_summary.append('Null')

            one_sum = '~~'.join(one_summary)
            all_summary.append(one_sum)

        all_summeries = '|'.join(all_summary)
        cr = self.env.cr
        cr.execute("select batch_create_summary(%s)", (all_summeries,))
        cr.commit()
        cr.savepoint()



