# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe

def execute():
	frappe.reload_doc("accounts", "doctype", "account")
	receivable_payable_accounts = create_receivable_payable_account()
	if receivable_payable_accounts:
		set_party_in_jv_and_gl_entry(receivable_payable_accounts)
		delete_individual_party_account()
		remove_customer_supplier_account_report()
		add_default_accounts_in_party(receivable_payable_accounts)


def link_warehouse_account():
	frappe.db.sql("""update tabAccount set warehouse=master_name
		where ifnull(account_type, '') = 'Warehouse' and ifnull(master_name, '') != ''""")

def create_receivable_payable_account():
	receivable_payable_accounts = frappe._dict()

	def _create_account(args):
		account = frappe.new_doc("Account")
		account.group_or_ledger = "Ledger"
		account.update(args)
		account.insert()

		frappe.db.set_value("Company", args["company"],
			("receivables_group" if args["account_type"]=="Receivable" else "payables_group"), account.name)

		receivable_payable_accounts.setdefault(args["company"], {}).setdefault(args["account_type"], account.name)

	for company in frappe.db.sql_list("select name from tabCompany"):
		_create_account({
				"account_name": "Debtors",
				"account_type": "Receivable",
				"company": company,
				"parent_account": get_parent_account(company, "Customer")
			})

		_create_account({
			"account_name": "Creditors",
			"account_type": "Payable",
			"company": company,
			"parent_account": get_parent_account(company, "Supplier")
		})

	return receivable_payable_accounts

def get_parent_account(company, master_type):
	parent_account = frappe.db.get_value("Company", company,
		"receivables_group" if master_type=="Customer" else "payables_group")
	if not parent_account:
		parent_account = frappe.db.get_value("Account", {"company": company,
			"account_name": "Accounts Receivable" if master_type=="Customer" else "Accounts Payable"})

	if not parent_account:
		parent_account = frappe.db.sql_list("""select parent_account from tabAccount
			where company=%s and ifnull(master_type, '')=%s and ifnull(master_name, '')!='' limit 1""",
			(company, master_type))
		parent_account = parent_account[0][0] if parent_account else None

	return parent_account

def set_party_in_jv_and_gl_entry(receivable_payable_accounts):
	accounts = frappe.db.sql("""select name, master_type, master_name, company from `tabAccount`
		where ifnull(master_type, '') in ('Customer', 'Supplier') and ifnull(master_name, '') != ''""", as_dict=1)

	account_map = frappe._dict()
	for d in accounts:
		account_map.setdefault(d.name, d)

	if not account_map:
		return

	for dt in ["Journal Voucher Detail", "GL Entry"]:
		records = frappe.db.sql("""select name, account from `tab%s` where account in (%s)""" %
			(dt, ", ".join(['%s']*len(account_map))), tuple(account_map.keys()))
		for d in records:
			account_details = account_map.get(d.account, {})
			account_type = "Receivable" if account_details.get("master_type")=="Customer" else "Payable"
			new_account = receivable_payable_accounts[account_details.get("company")][account_type]

			frappe.db.sql("update `tab{0}` set account=%s, party_type=%s, party=%s where name=%s".format(dt),
				(new_account, account_details.get("master_type"), account_details.get("master_name"), d.name))

def delete_individual_party_account():
	frappe.db.sql("""delete from `tabAccount` where ifnull(master_type, '') in ('Customer', 'Supplier')
		and ifnull(master_name, '') != ''""")

def remove_customer_supplier_account_report():
	for d in ["Customer Account Head", "Supplier Account Head"]:
		frappe.delete_doc("Report", d)

def add_default_accounts_in_party(receivable_payable_accounts):
	for dt in ["Customer", "Supplier"]:
		for p in frappe.db.sql("""select name from `tab{0}` where docstatus < 2""".format(dt)):
			try:
				party = frappe.get_doc(dt, p[0])
				for company, accounts in receivable_payable_accounts.items():
					party.append("party_accounts", {
						"company": company,
						"account": accounts["Receivable" if dt == "Customer" else "Payable"]
					})
				party.save()
			except:
				pass