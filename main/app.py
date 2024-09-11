import json
import os
import logging
import pandas as pd
from main.utils.db_utils import DbUtils
from main.utils.s3_utils import S3Utils
from main.utils.rag_utils import RagUtils
from main.utils.logger_utils import logger
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import requests
from datetime import datetime, timedelta
import yfinance as yf
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
import pdfkit
import base64
from flask import Flask, render_template, request, jsonify, redirect
import threading
import matplotlib.dates as mdates
import re

app = Flask(__name__)
subscription_lock = threading.Lock()

REPORT_TYPES = {
    'industry_news': {
        'report_id': 'industry_news',
        'report_name': 'Industry News Report',
        'report_function': 'generate_industry_news_report',
        'report_html': 'industry_news_report_template.html',
        'report_css': 'industry_news_report.css'
    },
    'daily_report': {
        'report_id': 'daily_report',
        'report_name': 'Daily Company Report',
        'report_function': 'generate_daily_company_report',
        'report_html': 'daily_company_report_template.html',
        'report_css': 'daily_company_report.css'
    },
    'director_trades': {
        'report_id': 'director_trades',
        'report_name': 'Changes in Director Interests',
        'report_function': 'generate_director_trades_report',
        'report_html': 'director_trades_report_template.html',
        'report_css': 'director_trades_report.css'
    }
}


class ReportGenerator:
    def __init__(self, s3, db, rag_utils):
        template_dir = os.path.join(os.getcwd(), 'templates')

        # Check if the template directory exists
        if not os.path.exists(template_dir):
            logging.error(f"Template directory does not exist: {template_dir}")
            raise FileNotFoundError(f"Template directory does not exist: {template_dir}")

        self.env = Environment(loader=FileSystemLoader(template_dir))
        self.s3 = s3
        self.db = db
        self.rag_utils = rag_utils
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def encode_image(image_path):
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded_string}"

    @staticmethod
    def parse_json(json_string):
        """
        Parses a JSON string and returns a Python dictionary.
        If the string is empty or invalid, it logs a notice and returns an empty dictionary.

        :param json_string:
        :return: Parsed dictionary or empty dictionary
        """
        if not json_string:
            logger.info("Details provided are empty.")
            return {}

        try:
            # Attempt to parse the JSON string into a dictionary
            return json.loads(json_string)
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON format: {e}")
            return {}


    def render_template_to_html_and_pdf(self, report_data, output_path):
        try:
            # Extract the report header and body template names from the report_data structure
            report_header_template_name = report_data.get("report_header", {}).get("template_name")
            body_template_name = report_data.get("report_body", {}).get("template_name")

            if not report_header_template_name:
                raise ValueError("No report header template name provided in the report data.")
            if not body_template_name:
                raise ValueError("No report body template name provided in the report data.")

            # Encode images (e.g., DHI logo)
            report_data["dhi_logo"] = self.encode_image("static/dhi_logo.png")

            report_data['static_url'] = lambda filename: f"/static/{filename}"

            # Render the master template (header) with the entire report_data, including the body data
            self.logger.debug(f"Rendering master template with embedded template: {report_header_template_name}")
            master_template = self.env.get_template(report_header_template_name)

            final_html_content = master_template.render(report_data)

            # Debugging: Log the final HTML content
            self.logger.debug(f"Final HTML content:\n{final_html_content}")

            # Extract report orientation from the report_data
            report_orientation = report_data.get("report_header", {}).get("report_orientation", "Portrait")

            # Generate the PDF from the final HTML content
            options = {
                'enable-local-file-access': None,
                'orientation': report_orientation
            }
            static_folder = os.path.join(os.getcwd(), 'static')
            stylesheets = [
                os.path.join(static_folder, report_data["report_header"]["header_css"]),
                os.path.join(static_folder, report_data["report_body"]["body_css"])
            ]

            pdfkit.from_string(final_html_content, output_path, options=options, css=stylesheets)

            self.logger.info(f"Generated PDF: {output_path}")
            return output_path, final_html_content

        except TemplateNotFound as e:
            self.logger.error(f"Template not found: {e}")
            raise
        except FileNotFoundError as e:
            self.logger.error(f"File not found: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to generate PDF: {e}")
            raise

    def generate_industry_news_report(self, details):
        self.logger.info(f"Generating Industry News report: {details}...")
        report_info = REPORT_TYPES.get('industry_news')
        industry_code = details
        if not industry_code:
            self.logger.error("Industry code (subscription_value) is missing in the details provided.")
            raise ValueError("Industry code is required to generate the report.")

        #results = self.db.get_industry_data(industry_code)

        report_data = {
            "report_header": {
                "template_name": "report_header.html",
                "report_name": f"{report_info['report_name']}: {industry_code}",
                "generation_date": datetime.now().strftime("%Y-%m-%d"),
                "report_orientation": "Portrait",
                "header_css": 'report_header.css'
            },
            "report_body": {
                "template_name":  report_info['report_html'],
                "generation_date": datetime.now().strftime("%Y-%m-%d"),
                "body_css": report_info['report_css']
            }
        }

        # Render the templates to HTML and PDF
        pdf_filename, report_html = self.render_template_to_html_and_pdf(
            report_data,
            output_path=os.path.join(os.getcwd(), 'output',
                                     f"industry_news_report_{industry_code}_{datetime.now().strftime('%Y-%m-%d')}.pdf")
        )
        return pdf_filename, report_html

    def generate_daily_company_report(self, details):
        self.logger.info("Generating Daily Company Report...")
        report_info = REPORT_TYPES.get('daily_report')
        # Parse the details JSON string
        try:
            details_dict = self.parse_json(details)
        except ValueError as e:
            self.logger.error(f"Error in parsing details: {e}")
            raise

        # Extract the ASX code
        asx_code = details_dict.get('asx_code')

        if not asx_code:
            self.logger.error("ASX code (subscription_value) is missing in the details provided.")
            raise ValueError("ASX code is required to generate the report.")

        # Fetch company summary and details
        results = self.db.get_company_summary(asx_code)
        company_summary = results['company_summary']
        company_name = results['company_name']
        company_logo_path = self.s3.fetch_logo_from_s3(asx_code)

        # Fetch and plot the company's stock price
        stock_symbol = f"{asx_code}.AX"
        stock_data = yf.download(stock_symbol, period="5d", interval="1d")
        last_price = stock_data['Close'][-1]
        previous_price = stock_data['Close'][-2]
        percentage_change = ((last_price - previous_price) / previous_price) * 100
        line_color = 'blue' if last_price > previous_price else 'red'

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(stock_data['Close'], color=line_color, linewidth=2)
        ax.fill_between(stock_data.index, stock_data['Close'], color=line_color, alpha=0.1)
        ax.plot(stock_data.index[-1], last_price, marker='o', color=line_color, markersize=8)
        ax.grid(True, which='major', axis='y', linestyle='--', linewidth=0.5, color='gray')
        ax.set_xlabel('')
        ax.set_ylabel('Price (AUD)', fontsize=12)
        plt.xticks(rotation=45)

        plt.figtext(0.15, 0.92, f"{company_name} ({asx_code})", fontsize=16, weight='bold', ha='left')
        plt.figtext(0.15, 0.86, f"${last_price:.2f}", fontsize=24, weight='bold', ha='left')
        change_color = 'green' if percentage_change > 0 else 'red'
        percentage_text = f"{percentage_change:.2f}%"
        box_props = dict(boxstyle="round,pad=0.3", facecolor=change_color, edgecolor=change_color)
        plt.figtext(0.32, 0.86, percentage_text, fontsize=16, color='white', ha='left', bbox=box_props)

        plt.subplots_adjust(top=0.8)
        stock_chart_path = os.path.join(os.getcwd(), 'output', f"{asx_code}_stock_chart.png")
        plt.savefig(stock_chart_path, dpi=300, bbox_inches='tight')
        plt.close()

        # RAG Queries
        prompts = [
            f"Provide me a summary of recent activities, for company: {asx_code}",
            f"Provide me a media update and sentiment and reflections, for company: {asx_code}",
            f"Tell me about recent director trades, for company: {asx_code}",
            f"Summarize key activities disclosed by {asx_code} over the last 7 days in a bullet-point list. "
            "Focus on:\n\n"
            " - Financial updates\n"
            " - Product or service launches\n"
            " - Strategic initiatives (e.g., mergers, acquisitions)\n"
            " - Operational changes (e.g., leadership, restructuring)\n"
            " - Market activity (e.g., stock buybacks, investments)\n"
            " - Regulatory updates\n"
            " - Sustainability actions\n"
            " - Partnerships\n"
            " - Customer announcements\n"
            " - Industry recognition\n\n"
            "Present each as a separate bullet point, and skip categories with no updates."
        ]
        rag_responses = [self.rag_utils.ask_question(prompt)[0] for prompt in prompts]

        # Prepare the template contexts
        report_data = {
            "report_header": {
                "template_name": "report_header.html",
                "report_name": f"{report_info['report_name']}: {company_name} [{asx_code}]",
                "company_name": company_name,
                "generation_date": datetime.now().strftime("%Y-%m-%d"),
                "report_orientation": "Portrait",
                "header_css":  'report_header.css'
            },
            "report_body": {
                "template_name":  report_info['report_html'],
                "company_summary": company_summary,
                "company_logo": self.encode_image(company_logo_path),
                "stock_chart": self.encode_image(stock_chart_path),
                "recent_activities":  self.format_rag_response(rag_responses[0]),
                "media_update": self.format_rag_response(rag_responses[1]),
                "director_trades":  self.format_rag_response(rag_responses[2]),
                "key_updates": self.format_rag_response(rag_responses[3]),
                "generation_date": datetime.now().strftime("%Y-%m-%d"),
                "body_css": report_info['report_css']
            }
        }

        print (self.format_rag_response(rag_responses[3]))
        # Render the templates to a PDF
        pdf_filename, report_html = self.render_template_to_html_and_pdf(
            report_data,
            output_path=os.path.join(os.getcwd(), 'output',
                                     f"daily_company_report_{asx_code}_{datetime.now().strftime('%Y-%m-%d')}.pdf")
        )

        # Clean up the temporary chart image
        os.remove(stock_chart_path)
        return pdf_filename, report_html


    def format_rag_response(self, rag_response):
        """
        Cleans up inconsistent Markdown-like formatting and converts it into structured HTML.
        Removes only the first line if it's a top-level title and formats the remaining content into HTML.
        Handles headers, bold text, lists, and ensures proper paragraph spacing.
        Returns a well-formatted HTML string.
        """

        # Strip the first line if it looks like a top-level title (e.g., bold or header text)
        rag_response = re.sub(r'^\s*(#|\*\*|##|###).*\n', '', rag_response, count=1)

        # Normalize headers: convert any remaining `#`, `##`, etc., to <h2> and <h3> tags
        cleaned_response = re.sub(r'^\s*#{1,2}\s+(.*)', r'<h2>\1</h2>', rag_response, flags=re.MULTILINE)
        cleaned_response = re.sub(r'^\s*#{3,6}\s+(.*)', r'<h3>\1</h3>', cleaned_response, flags=re.MULTILINE)

        # Normalize bold and italic: convert `**text**` or `__text__` to <strong> and `*text*` or `_text_` to <em>
        cleaned_response = re.sub(r'(\*\*|__)(.*?)\1', r'<strong>\2</strong>', cleaned_response)  # Bold to <strong>
        cleaned_response = re.sub(r'(\*|_)(.*?)\1', r'<em>\2</em>', cleaned_response)            # Italic to <em>

        # Convert unordered and ordered lists into <ul><li> (both numbered and bullet lists)
        cleaned_response = re.sub(r'^\s*[\*\-\+]\s+(.*)', r'<li>\1</li>', cleaned_response, flags=re.MULTILINE)  # Unordered lists
        cleaned_response = re.sub(r'^\s*\d+\.\s+(.*)', r'<li>\1</li>', cleaned_response, flags=re.MULTILINE)     # Numbered lists

        # Wrap consecutive <li> items in <ul> tags for bullet points
        cleaned_response = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', cleaned_response, flags=re.DOTALL)

        # Ensure paragraphs are properly separated: replace multiple newlines with <p> tags
        cleaned_response = re.sub(r'\n{2,}', '</p><p>', cleaned_response)

        # Wrap the entire content in a <div> and ensure it starts with a <p> tag
        cleaned_response = f"<div><p>{cleaned_response}</p></div>"

        # Clean up any excessive spaces or empty tags
        cleaned_response = re.sub(r'\s+', ' ', cleaned_response)  # Remove extra spaces
        cleaned_response = re.sub(r'<p>\s*</p>', '', cleaned_response)  # Remove empty paragraphs

        return cleaned_response


    def generate_director_trades_report(self, details):
        self.logger.info("Generating Director Trade Report...")
        report_info = REPORT_TYPES.get('director_trades')
        try:
            details_dict = self.parse_json(details)
        except ValueError as e:
            self.logger.error(f"Error in parsing details: {e}")
            raise

        # Extract the ASX code, default to 'ASX' if missing
        asx_code = details_dict.get('asx_code')
        is_company_specific = True
        if not asx_code:
            company_name = 'ALL'
            asx_code = 'ASX'
            is_company_specific = False
        else:
            # Fetch company summary and details
            results = self.db.get_company_summary(asx_code)
            company_name = results['company_name']

        try:
            company_logo_path = self.s3.fetch_logo_from_s3(asx_code)
        except Exception as e:
            self.logger.warning(f"Company logo for {asx_code} not found: {e}")
            company_logo_path = None

        date_from = details_dict.get('date_from')
        date_to = details_dict.get('date_to')
        frequency = details_dict.get('frequency')

        db_params = {}
        if is_company_specific:
            db_params['asx_code'] = asx_code
        if date_from:
            db_params['date_from'] = date_from
        if date_to:
            db_params['date_to'] = date_to
        if frequency:
            frequency = int(frequency)
            db_params['date_from'] = datetime.now() - timedelta(days=frequency)
            db_params['date_to'] = datetime.now()
        # Fetch data and drop unnecessary columns
        director_trades_raw = self.db.get_director_trades(**db_params)

        if director_trades_raw is None or director_trades_raw.empty:
            # Log a notice if no records are found and handle it gracefully
            self.logger.info("No director trades found for the given criteria.")
            director_trades_html = "<p>No director trades available for the selected criteria.</p>"
        else:
            # Drop unnecessary columns
            director_trades_raw = director_trades_raw.drop(columns=['Indirect Interest Nature', 'ABN', 'Change Nature'])

            # Convert 'date_of_change' to datetime, errors='coerce' will set invalid parsing to NaT (Not a Time)
            director_trades_raw['Date Of Change'] = pd.to_datetime(director_trades_raw['Date Of Change'], errors='coerce')

            # Sort by 'date_of_change' in descending order
            director_trades_raw = director_trades_raw.sort_values(by='Date Of Change', ascending=False)

            # Convert to HTML for rendering
            director_trades_html = director_trades_raw.to_html(classes='dataframe', index=False)

        report_data = {
            "report_header": {
                "template_name": "report_header.html",
                "report_name": f"{report_info['report_name']}: {company_name} [{asx_code}]",
                "company_name": company_name,
                "generation_date": datetime.now().strftime("%Y-%m-%d"),
                "report_orientation": "Portrait",
                "header_css": 'report_header.css'
            },
            "report_body": {
                "template_name":  report_info['report_html'],
                "company_logo": self.encode_image(company_logo_path),
                "director_trades": director_trades_html,
                "generation_date": datetime.now().strftime("%Y-%m-%d"),
                "body_css": report_info['report_css']
            }
        }

        # Render the templates to HTML and PDF
        pdf_filename, report_html = self.render_template_to_html_and_pdf(
            report_data,
            output_path=os.path.join(os.getcwd(), 'output',
                                     f"director_trades_report_{asx_code}_{datetime.now().strftime('%Y-%m-%d')}.pdf")
        )
        return pdf_filename, report_html


class ReportSender:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_email(self, email_title, report_filename, recipients):
        """Send email with the report as a PDF attachment."""
        self.logger.info(f"Preparing to send email report {report_filename} to {len(recipients)} recipients...")

        email_sender = os.environ.get("EMAIL_SENDER")
        email_provider = os.environ.get("EMAIL_PROVIDER", "mailhog").lower()

        if email_provider == "mailchimp":
            smtp_server = os.environ.get("SMTP_SERVER", "smtp.mandrillapp.com")
            smtp_port = int(os.environ.get("SMTP_PORT", 587))  # Use Mailchimp's SMTP port
            email_password = os.environ.get("EMAIL_PASSWORD")
        else:  # Default to MailHog
            smtp_server = os.environ.get("LOCAL_SMTP_SERVER", "localhost")
            smtp_port = int(os.environ.get("LOCAL_SMTP_PORT", 1025))  # Use MailHog's SMTP port
            email_password = None  # No password needed for MailHog

        # Ensure the file has a .pdf extension
        if not report_filename.endswith('.pdf'):
            report_filename += '.pdf'

        msg = MIMEMultipart()
        msg['Subject'] = email_title
        msg['From'] = email_sender
        msg['To'] = ", ".join(recipients)

        # Attach the PDF
        with open(report_filename, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            base_filename = os.path.basename(report_filename)
            part.add_header("Content-Disposition", f"attachment; filename='{base_filename}'")
            msg.attach(part)

        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.ehlo()
                if email_provider == "mailchimp":
                    server.starttls()
                    server.ehlo()
                    server.login(email_sender, email_password)
                server.sendmail(msg['From'], recipients, msg.as_string())
                self.logger.info(f"Email report {report_filename} sent successfully to {len(recipients)} recipients.")
        except smtplib.SMTPAuthenticationError as auth_err:
            self.logger.error(f"Authentication failed for {report_filename}: {auth_err}")
        except Exception as e:
            self.logger.error(f"Failed to send email report {report_filename}: {e}")

    def send_api(self, report_filename, endpoints):
        """Send report via API."""
        self.logger.info(f"Sending API report {report_filename} to {len(endpoints)} endpoints...")

        with open(report_filename, "rb") as file:
            report_data = file.read()

        for endpoint in endpoints:
            try:
                response = requests.post(endpoint, files={'file': report_data})
                response.raise_for_status()
                self.logger.info(f"Report {report_filename} sent to API endpoint {endpoint} successfully.")
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Failed to send report {report_filename} to API endpoint {endpoint}: {e}")

    def publish_rss(self, report_filename, feeds):
        """Publish report to RSS feeds."""
        self.logger.info(f"Publishing RSS report {report_filename} to {len(feeds)} feeds...")

        for feed in feeds:
            try:
                # Assuming a simple post to the RSS feed URL with the report data
                with open(report_filename, "rb") as file:
                    report_data = file.read()

                response = requests.post(feed, data=report_data)
                response.raise_for_status()
                self.logger.info(f"Report {report_filename} published to RSS feed {feed} successfully.")
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Failed to publish report {report_filename} to RSS feed {feed}: {e}")


#Flask end points for viewing reports
@app.route('/')
def list_subscriptions():
    db = DbUtils()
    subscriptions = db.get_distribution_preferences()
    customers = db.get_customers()

    # Extract report_ids from the REPORT_TYPES dictionary
    report_ids = [report['report_id'] for report in REPORT_TYPES.values()]

    return render_template('subscriptions.html', subscriptions=subscriptions, report_ids=report_ids,
                           customers=customers)


@app.route('/report/<subscription_type>/<subscription_value>')
@app.route('/report/<subscription_type>/', defaults={'subscription_value': None})
@app.route('/report/<subscription_type>', defaults={'subscription_value': None})
def view_report(subscription_type, subscription_value):
    report_generator = ReportGenerator(S3Utils(), DbUtils(), RagUtils())

    # Fetch the report details from the REPORT_TYPES dictionary
    report_info = REPORT_TYPES.get(subscription_type)

    # Check if the subscription_type exists in REPORT_TYPES
    if not report_info:
        return f"Unknown subscription type: {subscription_type}", 400

    # Dynamically call the appropriate report function
    report_function = getattr(report_generator, report_info['report_function'])

    # Generate the report by calling the function dynamically
    pdf_filename, report_html = report_function(subscription_value)

    # Return the HTML content directly, not using render_template_string
    return report_html


@app.route('/toggle_preference_active', methods=['POST'])
def toggle_preference_active():
    """
    Toggle the is_active status of a preference.
    Expects a POST request with JSON payload containing 'preference_id' and 'is_active'.
    """
    db_utils = DbUtils()
    try:
        data = request.get_json()

        # Extract preference_id and is_active from the JSON payload
        preference_id = data.get('preference_id')
        is_active = data.get('is_active')

        if preference_id is None or is_active is None:
            return jsonify({"error": "Invalid request payload"}), 400

        # Call the DB function to toggle the activation status
        new_status = db_utils.toggle_preference_active(preference_id, is_active)

        # Return the new status in the response
        return jsonify({"preference_id": preference_id, "new_status": new_status}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/save_preference', methods=['POST'])
def save_preference():
    """
    Endpoint to save the updated preference details.
    Expects a POST request with JSON payload containing the updated preference data.
    """
    db_utils = DbUtils()
    data = request.get_json()

    # Ensure all necessary fields are provided
    required_fields = ['preference_id', 'preference_type', 'preference_value', 'subscription_type',
                       'subscription_value', 'is_active']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Invalid request, missing fields"}), 400

    try:
        # Call the database update function
        db_utils.update_preference(
            data['preference_id'],
            data['preference_type'],
            data['preference_value'],
            data['subscription_type'],
            data['subscription_value'],
            data['is_active']
        )
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/delete_preference', methods=['POST'])
def delete_preference():
    """
    Endpoint to delete a preference.
    Expects a POST request with JSON payload containing the preference_id.
    """
    db_utils = DbUtils()
    data = request.get_json()

    # Ensure preference_id is provided
    if 'preference_id' not in data:
        return jsonify({"error": "Invalid request, 'preference_id' is required"}), 400

    try:
        # Call the database delete function
        db_utils.delete_preference(data['preference_id'])
        return jsonify({"success": True, "message": "Preference deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/save_new_subscription', methods=['POST'])
def save_new_subscription():
    customer_id = request.form['customer_id']
    preference_type = request.form['preference_type']
    preference_value = request.form['preference_value']
    subscription_type = request.form['subscription_type']
    subscription_value = request.form['subscription_value']
    is_active = request.form['is_active']

    # Insert into the database (you can implement the logic in DbUtils)
    db = DbUtils()
    db.insert_new_subscription(customer_id, preference_type, preference_value, subscription_type, subscription_value,
                               is_active)

    return redirect('/')  # Redirect back to the subscription list page


@app.route('/add_customer', methods=['POST'])
def add_customer():
    db_utils = DbUtils()
    data = request.get_json()

    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')

    if not all([first_name, last_name, email]):
        return jsonify({'success': False, 'message': 'Missing data. Please provide all required fields.'}), 400

    # Add customer to the database and get the result
    result = db_utils.add_customer(first_name, last_name, email)

    if result['success']:
        return jsonify({'success': True, 'message': result['message']}), 200
    else:
        return jsonify({'success': False, 'message': result['message']}), 400


@app.route('/run_subscriptions', methods=['POST'])
def run_subscriptions_endpoint():
    # Check if the lock is already acquired (i.e., another subscription process is running)
    if subscription_lock.locked():
        return jsonify({'success': False, 'message': 'Subscriptions are already running.'}), 400

    # Acquire the lock to prevent concurrent execution
    with subscription_lock:
        try:
            # Run the subscription process
            run_subscriptions()
            return jsonify({'success': True, 'message': 'Subscriptions are running.'}), 200
        except Exception as e:
            return jsonify({'success': False, 'message': f"Failed to run subscriptions: {str(e)}"}), 500


def run_subscriptions():
    db = DbUtils()
    s3 = S3Utils()
    rag_utils = RagUtils()
    report_generator = ReportGenerator(s3, db, rag_utils)
    report_sender = ReportSender()
    print(f"Processing reports for preference type: TEST")
    # Fetch distribution lists by preference type first, then by subscription type
    distribution_lists = db.get_distribution_lists_by_subscription()

    for preference_type, subscriptions in distribution_lists.items():
        logger.info(f"Processing reports for preference type: {preference_type}")

        if preference_type == "email":
            for subscription_type, subscription_values in subscriptions.items():
                logger.info(f"Processing subscription type: {subscription_type}")

                for subscription_value, emails in subscription_values.items():
                    logger.info(
                        f"Generating report for subscription type: {subscription_type}, subscription value: {subscription_value}")

                    report_info = REPORT_TYPES.get(subscription_type)
                    email_title = 'DHI Report Subscription: ' + report_info['report_name'] + " for " + datetime.now().strftime("%d %B %Y")

                    if not report_info:
                        logger.warning(f"Unknown subscription type: {subscription_type}")
                        continue
                    report_function = getattr(report_generator, report_info['report_function'])

                    # Generate the report
                    report_filename, _ = report_function(subscription_value)

                    # Send the generated report to each email in the list
                    logger.info(
                        f"Sending email reports for {subscription_type}, subscription value: {subscription_value}")
                    report_sender.send_email(email_title, report_filename, emails)

        elif preference_type == "api":
            logger.info(f"Processing API reports for preference type: {preference_type}")
            # Placeholder for API transmission logic
            # You can add logic here to handle API-based reports

        elif preference_type == "rss":
            logger.info(f"Processing RSS reports for preference type: {preference_type}")
            # Placeholder for RSS transmission logic
            # You can add logic here to handle RSS-based reports

        else:
            logger.warning(f"Unknown preference type: {preference_type}")
            continue  # Skip to the next preference type

    # Optionally log the distribution for tracking purposes
    logger.info("All reports have been processed and sent.")


def main():
    logger.info("Starting application...")
    view_mode = os.environ.get("VIEW_MODE", "False").lower() == "true"
    flask_port = int(os.environ.get("FLASK_PORT", "5000"))
    print (flask_port)
    if view_mode:
        # Start the Flask server
        app.run(debug=True, host="0.0.0.0", port=flask_port)
    else:
        run_subscriptions()


if __name__ == "__main__":
    main()
