from flask import Flask,request,render_template
from openai import OpenAI
import shelve
import os
import time
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()
OPEN_AI_API_KEY = os.getenv("OPEN_AI_API_KEY")
client = OpenAI(api_key=OPEN_AI_API_KEY)

# Access the environment variables
twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER")


twilio_client = Client(twilio_account_sid, twilio_auth_token)


def send_sms(to, message):
    # Send an SMS using Twilio
    try:
        message_sent = twilio_client.messages.create(
            body=message,
            from_=twilio_phone_number,
            to=to
        )
        print(f"Message sent successfully: {message_sent.sid}")
    except Exception as e:
        print(f"Error sending SMS: {e}")

@app.route('/get_chat_history/<phone_number>')
def get_chat_history(phone_number):
    with shelve.open("threads_db") as threads_shelf:
        chat_history = threads_shelf.get(phone_number, [])
    return {"history": chat_history}


@app.route('/')
def index():
    return render_template('index.html')



@app.route('/list_users')
def list_users():
    with shelve.open("threads_db") as threads_shelf:
        users = list(threads_shelf.keys())
    return {"users": users}





@app.route('/sms', methods=['POST'])
def sms():
    print("Request data:", request.form)
    incoming_message = request.form.get("Body")
    from_number = request.form.get("From")
    sender_name = request.form.get("ProfileName")

    # print(incoming_message)

    # Process the user's message and generate a response
    respoonse = generate_response(incoming_message, from_number, sender_name)
    print(f"Generated response text: '{respoonse}'")

    if respoonse:
        # Send the response text as an SMS using Twilio
        send_sms(from_number, respoonse)
    else:
        print("Response text is empty, not sending SMS.")

    return "Message sent"
    



# --------------------------------------------------------------
# Upload file
# --------------------------------------------------------------
def upload_file(path):
    # Upload a file with an "assistants" purpose
    file = client.files.create(file=open(path, "rb"), purpose="assistants")
    return file


file = upload_file("data/airbnb-faq.pdf")


# --------------------------------------------------------------
# Create assistant
# --------------------------------------------------------------
def create_assistant(file):
    """
    You currently cannot set the temperature for Assistant via the API.
    """
    assistant = client.beta.assistants.create(
        name="WhatsApp AirBnb Assistant",
        instructions="You're a helpful WhatsApp assistant that can assist guests that are staying in our Paris AirBnb. Use your knowledge base to best respond to customer queries. If you don't know the answer, say simply that you cannot help with question and advice to contact the host directly. Be friendly and funny.",
        tools=[{"type": "retrieval"}],
        model="gpt-4-1106-preview",
        file_ids=[file.id],
    )
    return assistant


# assistant = create_assistant(file)


# --------------------------------------------------------------
# Thread management
# --------------------------------------------------------------
def store_thread(from_number, thread_id):
    with shelve.open("threads_db", writeback=True) as threads_shelf:
        threads_shelf[from_number + "_thread_id"] = thread_id

def check_if_thread_exists(from_number):
    with shelve.open("threads_db") as threads_shelf:
        return threads_shelf.get(from_number + "_thread_id", None)



# --------------------------------------------------------------
# Generate response
# --------------------------------------------------------------
def generate_response(message_body, from_number, name):
    # Check if there is already a thread_id for the wa_id
    thread_id = check_if_thread_exists(from_number)

    # If a thread doesn't exist, create one and store it
    if thread_id is None:
        print(f"Creating new thread for {name} with wa_id {from_number}")
        thread = client.beta.threads.create()
        store_thread(from_number, thread.id)
        thread_id = thread.id

    # Otherwise, retrieve the existing thread
    else:
        print(f"Retrieving existing thread for {name} with wa_id {from_number}")
        thread = client.beta.threads.retrieve(thread_id)

    # Add message to thread
    message = client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message_body,
    )

    # Run the assistant and get the new message
    new_message = run_assistant(thread)
    print(f"To {name}:", new_message)

    # Store chat history
    store_chat_history(from_number, message_body, new_message)

    return new_message


def store_chat_history(phone_number, user_message, assistant_message):
    with shelve.open("threads_db", writeback=True) as threads_shelf:
        chat_key = phone_number + "_chat"
        if chat_key not in threads_shelf:
            threads_shelf[chat_key] = []

        threads_shelf[chat_key].append({"user": user_message, "assistant": assistant_message})


# --------------------------------------------------------------
# Run assistant
# --------------------------------------------------------------
def run_assistant(thread):
    # Retrieve the Assistant
    assistant = client.beta.assistants.retrieve("asst_ifcrrcHKvMm1LzxDYS8Wrlni")

    # Run the assistant
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )

    # Wait for completion
    while run.status != "completed":
        # Be nice to the API
        time.sleep(0.5)
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

    # Retrieve the Messages
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    new_message = messages.data[0].content[0].text.value
    print(f"Generated message: {new_message}")
    return new_message


# --------------------------------------------------------------
# Test assistant
# --------------------------------------------------------------


# new_message = generate_response(incoming_message,from_number , "khalid")

# new_message = generate_response("What's the check in time?", "123", "John")

# new_message = generate_response("What's the pin for the lockbox?", "456", "Sarah")

# new_message = generate_response("What was my previous question?", "123", "John")

# new_message = generate_response("What was my previous question?", "456", "Sarah")


if __name__ == '__main__':
    app.run(debug=True)