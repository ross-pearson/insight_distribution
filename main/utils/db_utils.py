import psycopg2
import os
from main.utils.logger_utils import logger
from main.utils.custom_error_utils import DatabaseError


class DbUtils:
    def __init__(self):
        self.dbname = os.environ.get('DB_NAME')
        self.username = os.environ.get('DB_USER')
        self.password = os.environ.get('DB_PASS')
        self.host = os.environ.get('DB_HOST')
        self.port = os.environ.get('DB_PORT')
        self.update_count = os.environ.get("UPDATE_COUNT", 5)

    def get_connection(self):
        conn = psycopg2.connect(
            dbname=self.dbname,
            user=self.username,
            password=self.password,
            host=self.host,
            port=self.port
        )
        return conn

    def select_all(self, query, params=None):
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        sql_results = cur.fetchall()
        cur.close()
        conn.close()
        return sql_results

    def get_external_ids(self):
        logger.info("Getting External Ids...")
        query = f"""SELECT d.external_id, dd.document_url, d.disclosure_id
                FROM disclosure.disclosure AS d
                INNER JOIN disclosure.disclosure_document AS dd
                ON d.disclosure_id = dd.disclosure_id
                WHERE (d.content IS NULL OR d.content = '' OR d.content='Failed to extract')
                LIMIT {self.update_count};
                """
        sql_results = DbUtils().select_all(query)
        if not sql_results:
            logger.info("No External ids with null content found in the db!!")
            exit(0)
        return sql_results

    def get_document_urls(self, external_ids):
        logger.info("Getting Document URLs")
        if isinstance(external_ids, list):
            external_ids_str = ", ".join(f"'{id}'" for id in external_ids)

        else:
            external_ids_str = ", ".join(f"'{id}'" for id in [external_ids])
        query = f"""
                SELECT d.external_id, dd.document_url, d.disclosure_id
                FROM disclosure.disclosure AS d
                INNER JOIN disclosure.disclosure_document AS dd
                ON d.disclosure_id = dd.disclosure_id
                WHERE d.external_id in({external_ids_str})
                """
        sql_results = DbUtils().select_all(query)
        if not sql_results:
            logger.error("No Document Urls found in db for the given external ids!!")
            raise DatabaseError("No Document Urls found in db for the given external ids!!")
        return sql_results

    def get_company_summary(self, asx_code):
        logger.info(f"Fetching disclosure summary for ASX code: {asx_code}...")
        query = """
            SELECT asx_code, company_name, company_summary 
            FROM disclosure.company 
            WHERE asx_code = %s;
        """
        sql_results = self.select_all(query, (asx_code,))
        if not sql_results:
            logger.info(f"No disclosures found in the database for ASX code: {asx_code}!")
            raise DatabaseError(f"No disclosures found in the database for ASX code: {asx_code}!")

        # Assuming the first result is the one we need
        result = sql_results[0]
        result_dict = {
            'asx_code': result[0],
            'company_name': result[1],
            'company_summary': result[2],
        }
        return result_dict

    def get_distribution_lists_by_subscription(self):
        logger.info("Fetching distribution lists by preference type and subscription type...")
        query = """
            SELECT dp.preference_type, dp.preference_value, dp.subscription_type, dp.subscription_value
            FROM insights.customers c
            JOIN insights.distribution_preferences dp ON c.customer_id = dp.customer_id
            WHERE dp.is_active = TRUE
            ORDER BY dp.preference_type, dp.subscription_type;
        """
        sql_results = self.select_all(query)
        if not sql_results:
            logger.info("No active distribution lists found in the database!")
            raise DatabaseError("No active distribution lists found in the database!")

        # Grouping by preference_type, then subscription_type, then subscription_value
        distribution_lists = {}
        for row in sql_results:
            preference_type = row[0]
            preference_value = row[1]
            subscription_type = row[2]
            subscription_value = row[3]

            if preference_type not in distribution_lists:
                distribution_lists[preference_type] = {}

            if subscription_type not in distribution_lists[preference_type]:
                distribution_lists[preference_type][subscription_type] = {}

            if subscription_value not in distribution_lists[preference_type][subscription_type]:
                distribution_lists[preference_type][subscription_type][subscription_value] = []

            # Add the preference_value (e.g., email) under the correct subscription_value
            distribution_lists[preference_type][subscription_type][subscription_value].append(preference_value)

        print (distribution_lists)
        return distribution_lists