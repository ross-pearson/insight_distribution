import os
import logging
from email.mime.image import MIMEImage
from email.mime.text import MIMEText

from pdf2image import convert_from_path

from main.utils.db_utils import DbUtils
from main.utils.s3_utils import S3Utils
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
import pdf2image


class ReportGenerator:
    def __init__(self, s3, db):
        self.s3 = s3
        self.db = db
        self.logger = logging.getLogger(__name__)

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

    def text_to_image(self, text, width=800, height=600, background_color=(255, 255, 255), text_color=(0, 0, 0), font_path=None, font_size=20):
        """Convert a given text to an image."""
        # Create a blank image with a white background
        image = Image.new('RGB', (width, height), color=background_color)
        draw = ImageDraw.Draw(image)

        # Load a font
        if font_path is None:
            font_path = os.path.join(os.getcwd(), 'static', 'arial.ttf')  # Update to the correct path of the font
        font = ImageFont.truetype(font_path, font_size)

        # Calculate text size and position using textbbox
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        text_width = right - left
        text_height = bottom - top

        text_x = (width - text_width) // 2
        text_y = (height - text_height) // 2

        # Draw the text on the image
        draw.text((text_x, text_y), text, font=font, fill=text_color)

        return image

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
            lines.append(line)
        return '\n'.join(lines)

    def generate_industry_news_pdf(self, details, industry):
        self.logger.info(f"Generating Industry News PDF for industry: {industry}...")

        # Example logic to fetch industry summary
        industry_summary = f"Summary for {industry}"  # Replace with actual logic to fetch summary
        image = self.text_to_image(industry_summary)
        image_path = os.path.join(os.getcwd(), 'output', 'industry_summary.png')
        image.save(image_path)

        industry_summary2 = f"Summary for {industry}"  # Replace with actual logic to fetch summary
        image2 = self.text_to_image(industry_summary2)
        image_path2= os.path.join(os.getcwd(), 'output', 'industry_summary.png')
        image2.save(image_path2)
        content = [image_path, image_path2]
        pdf_filename = self.generate_pdf(report_name='Industry News', content=content)
        os.remove(image_path)
        return pdf_filename

    def generate_daily_company_report_pdf(self, details):
        self.logger.info("Generating Daily Company Report PDF...")

        # Extract asx_code from the details dictionary
        asx_code = details
        if not asx_code:
            self.logger.error("ASX code (subscription_value) is missing in the details provided.")
            raise ValueError("ASX code is required to generate the report.")

        results = self.db.get_company_summary(asx_code)

        company_summary = results['company_summary']
        company_name = results['company_name']
        logo_path = self.s3.fetch_logo_from_s3(asx_code)

        # Load and resize the logo
        logo = Image.open(logo_path)
        max_logo_width = 100  # Smaller width for the logo
        max_logo_height = 50   # Smaller height for the logo
        logo.thumbnail((max_logo_width, max_logo_height), Image.LANCZOS)

        # Fetch and plot BHP stock price
        stock_symbol = f"{asx_code}.AX"  # BHP stock symbol on the ASX
        stock_data = yf.download(stock_symbol, period="5d", interval="1d")

        plt.figure(figsize=(8, 4))
        plt.plot(stock_data['Close'], marker='o')
        plt.title(f'{company_name} Stock Price')
        plt.xlabel('Date')
        plt.ylabel('Price (AUD)')
        plt.grid(True)

        # Save the chart as an image object (in-memory)
        chart_path = os.path.join(os.getcwd(), 'output', f'{asx_code}_stock_chart.png')
        plt.savefig(chart_path)
        plt.close()

        chart = Image.open(chart_path)

        # Create a blank canvas with enough height to fit both the summary and the chart
        image_width = 800
        summary_height = 400
        chart_height = 300
        image_height = summary_height + chart_height + 50  # 50 pixels extra for padding

        canvas = Image.new('RGB', (image_width, image_height), color=(255, 255, 255))  # White background
        draw = ImageDraw.Draw(canvas)

        # Load fonts
        font_path = os.path.join(os.getcwd(), 'static', 'arial.ttf')  # Update this path to the correct font path
        title_font = ImageFont.truetype(font_path, 40)
        summary_font = ImageFont.truetype(font_path, 20)

        # Position the logo and company name on the same line
        logo_x = 50  # Left margin for the logo
        logo_y = 50  # Top margin for the logo
        canvas.paste(logo, (logo_x, logo_y), logo)

        # Calculate the position for the company name
        text_width, text_height = draw.textbbox((0, 0), company_name, font=title_font)[2:]
        company_name_x = logo_x + logo.width + 20  # 20 pixels padding between logo and text
        company_name_y = logo_y + (logo.height - text_height) // 2  # Vertically centered with logo

        draw.text((company_name_x, company_name_y), company_name, font=title_font, fill=(0, 0, 0))

        # Draw a decorative line under the company name
        line_y = logo_y + logo.height + 20
        draw.line([(50, line_y), (image_width - 50, line_y)], fill=(0, 0, 0), width=3)

        # Wrap and draw the company summary text
        summary_y = line_y + 20
        wrapped_text = self.wrap_text(draw, company_summary, summary_font, image_width - 100)
        draw.multiline_text((50, summary_y), wrapped_text, font=summary_font, fill=(0, 0, 0))

        # Position the chart below the company summary
        chart_y = summary_y + 200  # Adjust this value to control spacing between summary and chart
        canvas.paste(chart, (50, chart_y))

        # Save the final image
        summary_image_path = os.path.join(os.getcwd(), 'output', f'{asx_code}_summary.png')
        canvas.save(summary_image_path)

        # Generate the PDF with the combined image
        content = [summary_image_path]
        pdf_filename = self.generate_pdf(report_name=f'{asx_code} Daily Company Report', content=content)

        # Clean up the temporary images
        os.remove(summary_image_path)
        os.remove(chart_path)

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
            smtp_server = os.environ.get("SMTP_SERVER", "localhost")
            smtp_port = int(os.environ.get("SMTP_PORT", 1025))  # Use MailHog's SMTP port
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
    report_generator = ReportGenerator(s3, db)
    report_sender = ReportSender()

    # Fetch distribution lists by preference type first, then by subscription type
    distribution_lists = db.get_distribution_lists_by_subscription()

    for preference_type, subscriptions in distribution_lists.items():
        logger.info(f"Processing reports for preference type: {preference_type}")

        if preference_type == "email":
            for subscription_type, subscription_values in subscriptions.items():
                logger.info(f"Processing subscription type: {subscription_type}")

                for subscription_value, emails in subscription_values.items():
                    logger.info(f"Generating report for subscription type: {subscription_type}, subscription value: {subscription_value}")

                    # Generate the report based on the subscription type and subscription value
                    if subscription_type == "industry news":
                        report_filename = report_generator.generate_industry_news_pdf(subscription_value)
                    elif subscription_type == "daily report":
                        report_filename = report_generator.generate_daily_company_report_pdf(subscription_value)
                    elif subscription_type == "market update":
                        report_filename = report_generator.generate_market_update_pdf(subscription_value)
                    else:
                        logger.warning(f"Unknown subscription type: {subscription_type}")
                        continue

                    # Send the generated report to each email in the list
                    logger.info(f"Sending email reports for {subscription_type}, subscription value: {subscription_value}")
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

if __name__ == "__main__":
    main()
