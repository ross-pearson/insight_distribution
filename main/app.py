import os
import logging
from main.utils.db_utils import DbUtils
from main.utils.s3_utils import S3Utils
from main.utils.rag_utils import RagUtils
from main.utils.logger_utils import logger
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import yfinance as yf
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
import pdfkit
import base64
from flask import Flask, render_template

app = Flask(__name__)

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

    def render_template_to_pdf(self, templates_with_contexts, output_path):
        try:
            # Extract template names
            cover_template_name = "cover_page_template.html"
            body_template_name = "daily_company_report_template.html"

            # Extract contexts
            cover_context = templates_with_contexts.get(cover_template_name)
            body_context = templates_with_contexts.get(body_template_name)

            if not cover_context:
                raise ValueError(f"Context for cover template '{cover_template_name}' not provided.")
            if not body_context:
                raise ValueError(f"Context for body template '{body_template_name}' not provided.")

            # Encode logo and background images
            def encode_image(image_path):
                with open(image_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    return f"data:image/png;base64,{encoded_string}"

            cover_context["dhi_logo"] = encode_image("static/dhi_logo.png")
            cover_context["background_uri"] = encode_image("static/background.png")

            # Render the cover template
            self.logger.debug(f"Rendering cover page with template: {cover_template_name}")
            cover_template = self.env.get_template(cover_template_name)
            cover_html = cover_template.render(cover_context)

            # Ensure the cover page content ends with a page break
            cover_html += '<div style="page-break-after: always;"></div>'

            # Render the main body template
            self.logger.debug(f"Rendering main body with template: {body_template_name}")
            body_template = self.env.get_template(body_template_name)
            body_html = body_template.render(body_context)

            # Combine the HTML content
            combined_html_content = cover_html + body_html

            # Debugging: Log the final combined HTML
            self.logger.debug(f"Final combined HTML content:\n{combined_html_content}")

            # Generate the PDF from the combined HTML content
            options = {'enable-local-file-access': None}
            pdfkit.from_string(combined_html_content, output_path, options=options)

            self.logger.info(f"Generated PDF: {output_path}")
            return output_path

        except TemplateNotFound as e:
            self.logger.error(f"Template not found: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to generate PDF: {e}")
            raise

    def generate_pdf(self, report_name='Report', content=None):
        """Generate a PDF with a title page and content pages with images."""
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Title Page
        pdf.add_page()

        # Background Image
        background_image = 'static/background.png'
        if os.path.exists(background_image):
            pdf.image(background_image, x=0, y=0, w=210, h=297)  # Full A4 size

        # White Box (80% of the page, centered)
        white_box_width = 210 * 0.8  # 80% of page width
        white_box_height = 297 * 0.8  # 80% of page height
        white_box_x = (210 - white_box_width) / 2  # Centered horizontally
        white_box_y = (297 - white_box_height) / 2  # Centered vertically

        pdf.set_fill_color(255, 255, 255)  # White color
        pdf.rect(white_box_x, white_box_y, white_box_width, white_box_height, 'F')

        # Company Logo inside the White Box
        logo_path = 'static/dhi_logo.png'
        if os.path.exists(logo_path):
            pdf.image(logo_path, x=white_box_x + 10, y=white_box_y + 10, w=30)  # Adjust size and position as needed

        # Title Box inside the White Box
        black_box_width = white_box_width * 0.8  # 80% of the white box width
        black_box_x = white_box_x  # Flush with the left side of the white box
        black_box_y = white_box_y + 60
        pdf.set_fill_color(0, 0, 0)  # Black color
        pdf.rect(black_box_x, black_box_y, black_box_width, 60, 'F')  # Position and size of the black box

        # Title Text inside the Black Box
        pdf.set_font("Arial", size=24)
        pdf.set_text_color(255, 255, 255)  # White text
        pdf.set_xy(black_box_x, black_box_y)
        pdf.cell(black_box_width, 60, report_name.upper(), 0, 1, 'C')

        # Company Information inside the White Box (left-aligned with padding)
        text_padding = white_box_x + 20  # 100px padding from the left
        pdf.set_text_color(0, 0, 0)  # Black text
        pdf.set_font("Arial", size=12)
        pdf.set_xy(text_padding, black_box_y + 80)
        pdf.cell(0, 10, "DHI-AI Pty Ltd", 0, 1, 'L')
        pdf.set_x(text_padding)
        pdf.cell(0, 10, datetime.now().strftime("%B %d, %Y"), 0, 1, 'L')
        pdf.set_x(text_padding)
        pdf.cell(0, 10, "website: dhi-ai.com", 0, 1, 'L')
        pdf.set_x(text_padding)
        pdf.cell(0, 10, "email: info@dhi-ai.com", 0, 1, 'L')

        # Content Pages
        if content:
            for index, image_data in enumerate(content, start=1):
                pdf.add_page()

                # Add header with report name
                pdf.set_font("Arial", size=16)
                pdf.set_y(10)  # Ensure the header is at the top
                pdf.cell(0, 10, report_name, 0, 1, 'C')

                # Add image
                pdf.image(image_data, x=10, y=20, w=190)  # Adjust image position to leave space for the header

                # Manually position footer at the bottom without causing a new page break
                pdf.set_y(-25)  # Move 25 units up from the bottom (15 for the text height, 10 for margin)
                pdf.set_font("Arial", size=8)
                pdf.cell(0, 10, f'Page {pdf.page_no()}', 0, 0, 'C')

        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"output/{report_name}_{current_time}.pdf"
        pdf.output(pdf_filename)
        self.logger.info(f"Generated PDF: {pdf_filename}")
        return pdf_filename

    def wrap_text(self, draw, text, font, max_width):
        """Wrap text to fit within a given width."""
        lines = []
        words = text.split()
        while words:
            line = ''
            while words:
                word = words[0]
                left, top, right, bottom = draw.textbbox((0, 0), line + word + ' ', font=font)
                if right - left <= max_width:
                    line += words.pop(0) + ' '
                else:
                    break
            lines.append(line.strip())  # Remove trailing space after last word in the line
        return lines

    def text_to_image(self, text, width=800, height=600, background_color=(255, 255, 255), text_color=(0, 0, 0),
                      font_path=None, font_size=20):
        """Convert a given text to an image."""
        # Create a blank image with a white background
        image = Image.new('RGB', (width, height), color=background_color)
        draw = ImageDraw.Draw(image)

        # Load a font
        if font_path is None:
            font_path = os.path.join(os.getcwd(), 'static', 'arial.ttf')  # Update to the correct path of the font
        font = ImageFont.truetype(font_path, font_size)

        # Wrap the text
        wrapped_lines = self.wrap_text(draw, text, font, max_width=width - 20)  # Leave some padding

        # Calculate the total height needed for the wrapped text
        total_text_height = sum(
            draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in
            wrapped_lines)

        # Start drawing text with vertical centering
        y = (height - total_text_height) // 2  # Center the text vertically
        for line in wrapped_lines:
            text_width, text_height = draw.textbbox((0, 0), line, font=font)[2:4]
            x = (width - text_width) // 2  # Center the text horizontally
            draw.text((x, y), line, font=font, fill=text_color)
            y += text_height  # Move to the next line vertically

        return image

    def generate_industry_news_pdf(self, details, industry):
        self.logger.info(f"Generating Industry News PDF for industry: {industry}...")

        # Example logic to fetch industry summary
        industry_summary = f"Summary for {industry}"  # Replace with actual logic to fetch summary
        image = self.text_to_image(industry_summary)
        image_path = os.path.join(os.getcwd(), 'output', 'industry_summary.png')
        image.save(image_path)

        industry_summary2 = f"Summary for {industry}"  # Replace with actual logic to fetch summary
        image2 = self.text_to_image(industry_summary2)
        image_path2 = os.path.join(os.getcwd(), 'output', 'industry_summary.png')
        image2.save(image_path2)
        content = [image_path, image_path2]
        pdf_filename = self.generate_pdf(report_name='Industry News', content=content)
        os.remove(image_path)
        return pdf_filename

    def generate_daily_company_report(self, details):
        self.logger.info("Generating Daily Company Report...")

        asx_code = details
        if not asx_code:
            self.logger.error("ASX code (subscription_value) is missing in the details provided.")
            raise ValueError("ASX code is required to generate the report.")

        # Fetch company summary and details
        results = self.db.get_company_summary(asx_code)
        company_summary = results['company_summary']
        company_name = results['company_name']
        logo_path = self.s3.fetch_logo_from_s3(asx_code)

        # Load and resize the logo
        logo = Image.open(logo_path)
        max_logo_width = 100
        max_logo_height = 50
        logo.thumbnail((max_logo_width, max_logo_height), Image.LANCZOS)

        # Convert the company logo to a base64 string to embed in HTML
        with open(logo_path, "rb") as logo_file:
            logo_data = base64.b64encode(logo_file.read()).decode('utf-8')
            logo_data_uri = f"data:image/png;base64,{logo_data}"

        # Fetch and plot the company's stock price
        stock_symbol = f"{asx_code}.AX"
        stock_data = yf.download(stock_symbol, period="5d", interval="1d")
        plt.figure(figsize=(8, 4))
        plt.plot(stock_data['Close'], marker='o')
        plt.title(f'{company_name} Stock Price')
        plt.xlabel('Date')
        plt.ylabel('Price (AUD)')
        plt.grid(True)

        # Save the stock chart to a file
        stock_chart_path = os.path.join(os.getcwd(), 'output', f'{asx_code}_stock_chart.png')
        plt.savefig(stock_chart_path)
        plt.close()

        # Convert stock chart to base64
        with open(stock_chart_path, "rb") as chart_file:
            chart_data = base64.b64encode(chart_file.read()).decode('utf-8')
            chart_data_uri = f"data:image/png;base64,{chart_data}"

        # RAG Queries
        prompts = [
            f"Provide me a summary of recent activities, for company: {asx_code}",
            f"Provide me an industry overview, for company: {asx_code}",
            f"Provide me a media update and sentiment and reflections, for company: {asx_code}",
            f"Tell me about recent director trades, for company: {asx_code}"
        ]
        rag_responses = [self.rag_utils.ask_question(prompt)[0] for prompt in prompts]

        # Prepare the template contexts
        templates_with_contexts = {
            "cover_page_template.html": {
                "report_name": f'Daily Company Report: {asx_code}',
                "company_name": company_name,
                "generation_date": datetime.now().strftime("%Y-%m-%d")
            },
            "daily_company_report_template.html": {
                "company_name": company_name,
                "company_summary": company_summary,
                "logo_data_uri": logo_data_uri,
                "stock_chart_data_uri": chart_data_uri,
                "recent_activities": rag_responses[0],
                "industry_overview": rag_responses[1],
                "media_update": rag_responses[2],
                "director_trades": rag_responses[3],
                "generation_date": datetime.now().strftime("%Y-%m-%d")
            }
        }

        # Render the templates to a PDF
        pdf_filename = self.render_template_to_pdf(
            templates_with_contexts,
            output_path=os.path.join(os.getcwd(), 'output',
                                     f"daily_company_report_{asx_code}_{datetime.now().strftime("%Y-%m-%d")}.pdf")
        )

        # Clean up the temporary chart image
        os.remove(stock_chart_path)
        return pdf_filename

    def generate_market_update_pdf(self, details):
        self.logger.info("Generating Market Update PDF...")
        # Placeholder for market update generation logic
        asx_code = 'ASX'  # Example ASX code; replace with logic specific to market updates
        company_summary = 'placeholder'
        logo_filename = "ASX"  # Replace with actual logo filename
        logo_path = self.s3.fetch_logo_from_s3(logo_filename)
        pdf_filename = self.generate_pdf(company_summary, logo_path)
        return pdf_filename


class ReportSender:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_email(self, report_filename, recipients):
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
        msg['Subject'] = "Your Report"
        msg['From'] = email_sender
        msg['To'] = ", ".join(recipients)

        # Attach the PDF
        with open(report_filename, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            base_filename = os.path.basename(report_filename)
            part.add_header("Content-Disposition", f'attachment; filename="{base_filename}"')
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


def main():
    logger.info("Starting application...")
    db = DbUtils()
    s3 = S3Utils()
    rag_utils = RagUtils()
    report_generator = ReportGenerator(s3, db, rag_utils)
    report_sender = ReportSender()

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

                    # Generate the report based on the subscription type and subscription value
                    if subscription_type == "industry news":
                        report_filename = report_generator.generate_industry_news_pdf(subscription_value)
                    elif subscription_type == "daily report":
                        report_filename = report_generator.generate_daily_company_report(subscription_value)
                    elif subscription_type == "market update":
                        report_filename = report_generator.generate_market_update_pdf(subscription_value)
                    else:
                        logger.warning(f"Unknown subscription type: {subscription_type}")
                        continue

                    # Send the generated report to each email in the list
                    logger.info(
                        f"Sending email reports for {subscription_type}, subscription value: {subscription_value}")
                    report_sender.send_email(report_filename, emails)

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


def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_string

@app.route('/')
def render_report():
    # Paths to images
    logo_path = "static/dhi_logo.png"
    background_image_path = "static/background.png"

    # Encode images to base64
    dhi_logo = encode_image_to_base64(logo_path)
    background_image_uri = encode_image_to_base64(background_image_path)

    # Prepare the context for the template
    cover_context = {
        "report_name": "Daily Company Report: AZS",
        "company_name": "Company Name Here",
        "generation_date": datetime.now().strftime("%Y-%m-%d"),
        "dhi_logo": f"data:image/png;base64,{dhi_logo}",
        "background_uri": f"data:image/png;base64,{background_image_uri}"
    }

    return render_template('cover_page_template.html', **cover_context)

if __name__ == "__main__":
    # using flask just to test HTML
    # app.run(debug=True)
    main()
