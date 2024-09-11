import psycopg2
import os
from main.utils.logger_utils import logger
from main.utils.custom_error_utils import DatabaseError
import ast
import pandas as pd


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

    def execute(self, query, params=None):
        """
        Execute an INSERT, UPDATE, or DELETE query.
        """
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(query, params)
            conn.commit()  # Commit the changes
        except Exception as e:
            conn.rollback()  # Rollback in case of error
            raise e
        finally:
            cur.close()
            conn.close()

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

    def get_company_director_trades_by_asx_code(self, asx_code):
        logger.info(f"Fetching company director trades for ASX code: {asx_code}...")

        query = """
            SELECT daa.external_id, daa.structured_text
            FROM disclosure.disclosure_attributes_annotations AS daa
            INNER JOIN disclosure.disclosure AS d
            ON daa.disclosure_id = d.disclosure_id 
            AND daa.attribute_id = '47bcf56f-19bf-403f-b491-21493f72b16c'
            INNER JOIN disclosure.company AS c
            ON d.company_id = c.company_id
            WHERE c.asx_code = %s;
        """

        # Execute the query with the passed asx_code
        sql_results = self.select_all(query, (asx_code,))
        if not sql_results:
            logger.info(f"No director trades found in the database for ASX code: {asx_code}!")
            raise DatabaseError(f"No director trades found in the database for ASX code: {asx_code}!")

        # Create a DataFrame from the results
        df = pd.DataFrame(sql_results, columns=['external_id', 'structured_text'])

        # Convert structured_text from string to dictionary
        df['structured_text'] = df['structured_text'].apply(ast.literal_eval)

        # Now you can extract everything from structured_text into separate columns
        structured_text_df = pd.json_normalize(df['structured_text'])

        # Combine the external_id with the expanded structured_text
        result_df = pd.concat([df[['external_id']], structured_text_df], axis=1)

        return result_df



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

    def get_distribution_preferences(self):
        logger.info("Fetching distribution lists by preference type and subscription type...")

        query = """
            SELECT CONCAT(c.first_name, ' ', c.last_name) as customer_name, dp.preference_id, dp.customer_id, dp.preference_type, dp.preference_value, dp.is_active, dp.subscription_type, dp.subscription_value
            FROM insights.distribution_preferences dp 
            INNER JOIN insights.customers c
            ON dp.customer_id = c.customer_id
            ORDER BY dp.preference_id;
        """

        sql_results = self.select_all(query)

        if not sql_results:
            logger.info("No customer preference lists found in the database!")
            raise DatabaseError("No customer preferences found in the database!")

        # Parse the SQL results into a list of dictionaries
        distribution_lists = []

        for row in sql_results:
            distribution_lists.append({
                "customer_name": row[0],
                "preference_id": row[1],            # Access by index
                "customer_id": row[2],
                "preference_type": row[3],
                "preference_value": row[4],
                "is_active": row[5],
                "subscription_type": row[6],
                "subscription_value": row[7]
            })

        return distribution_lists


    def get_customers(self):
        logger.info("Fetching distribution lists by preference type and subscription type...")

        query = """
            SELECT c.customer_id, c.first_name, c.last_name, c.email
            FROM insights.customers c 
            ORDER BY c.customer_id;
        """

        sql_results = self.select_all(query)

        if not sql_results:
            logger.info("No customers found in the database!")
            raise DatabaseError("No customers found in the database!")

        # Parse the SQL results into a list of dictionaries
        customers = []

        for row in sql_results:
            customers.append({
                "customer_id": row[0],            # Access by index
                "first_name": row[1],
                "last_name": row[2],
                "email": row[3]
            })

        return customers

    def toggle_preference_active(self, preference_id, is_active):
        """
        Toggles the is_active field in the distribution_preferences table.
        """
        logger.info(f"Toggling is_active status for preference_id {preference_id}. Current status: {is_active}")

        # Toggle the current status
        new_status = not is_active

        # SQL query to update the is_active field
        query = """
            UPDATE insights.distribution_preferences
            SET is_active = %s
            WHERE preference_id = %s;
        """

        # Execute the update query using the execute method
        self.execute(query, (new_status, preference_id))

        logger.info(f"Preference ID {preference_id} activation status changed to: {new_status}")

        return new_status

    def update_preference(self, preference_id, preference_type, preference_value, subscription_type, subscription_value, is_active):
        """
        Updates the distribution_preferences table with the new values.
        """
        query = """
            UPDATE insights.distribution_preferences
            SET preference_type = %s,
                preference_value = %s,
                subscription_type = %s,
                subscription_value = %s,
                is_active = %s
            WHERE preference_id = %s;
        """
        params = (preference_type, preference_value, subscription_type, subscription_value, is_active, preference_id)

        try:
            self.execute(query, params)
            logger.info(f"Preference ID {preference_id} updated successfully.")
        except Exception as e:
            logger.error(f"Failed to update preference ID {preference_id}: {e}")
            raise

    def delete_preference(self, preference_id):
        """
        Deletes a preference from the distribution_preferences table.
        """
        query = """
            DELETE FROM insights.distribution_preferences
            WHERE preference_id = %s;
        """
        params = (preference_id,)

        try:
            self.execute(query, params)
            logger.info(f"Preference ID {preference_id} deleted successfully.")
        except Exception as e:
            logger.error(f"Failed to delete preference ID {preference_id}: {e}")
            raise


    def insert_new_subscription(self, customer_id, preference_type, preference_value, subscription_type, subscription_value, is_active):
        query = """
            INSERT INTO insights.distribution_preferences (customer_id, preference_type, preference_value, subscription_type, subscription_value, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (customer_id, preference_type, preference_value, subscription_type, subscription_value, is_active)
        self.execute(query, params)

    def add_customer(self, first_name, last_name, email):
        """
        Inserts a new customer into the insights.customers table.
        Handles unique violation for duplicate emails gracefully.
        """
        query = """
            INSERT INTO insights.customers (first_name, last_name, email)
            VALUES (%s, %s, %s)
        """
        params = (first_name, last_name, email)

        try:
            self.execute(query, params)
            logger.info(f"Customer {first_name} {last_name} added successfully.")
            return {'success': True, 'message': f"Customer {first_name} {last_name} added successfully."}
        except psycopg2.errors.UniqueViolation as e:
            logger.error(f"Failed to add customer {first_name} {last_name}: Email {email} already exists.")
            return {'success': False, 'message': f"Email {email} already exists. Please use a different email."}
        except Exception as e:
            logger.error(f"Failed to add customer {first_name} {last_name}: {e}")
            return {'success': False, 'message': f"An error occurred while adding the customer: {e}"}
