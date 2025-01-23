const {
  TurnContext,
  CardFactory,
  MessageFactory,
  TeamsInfo,
  TeamsActivityHandler,
} = require("botbuilder");
const GraphHelper = require("../helpers/graphHelper");

/****/
// const fs = require("fs");
// async function writeToFile(filePath, data) {
//   console.log("jajajajaja");
//   try {
//     await fs.writeFile(filePath, data);
//     console.log(`File written successfully to ${filePath}`);
//   } catch (error) {
//     console.error("Error writing to file:", error);
//   }
// }
const sleep = (ms) => new Promise((res) => setTimeout(res, ms));
const axios = require("axios");
const PDFDocument = require("pdfkit");
const FormData = require("form-data");
const fs = require("fs");
/****/

class ActivityBot extends TeamsActivityHandler {
  constructor() {
    super();

    this.onMessage(async (context, next) => {
      // Remove recipient mention
      TurnContext.removeRecipientMention(context.activity);

      // Instantiate GraphHelper
      const graphHelper = new GraphHelper();

      // Get the user's ID from the activity
      const userId = context.activity.from.aadObjectId; // Use 'aadObjectId' for Azure AD-based user ID

      // Fetch user details
      const userDetails = await graphHelper.GetUserDetailsAsync(userId);

      if (userDetails) {
        console.log(`User Email: ${userDetails.mail}`);
        console.log(`User Display Name: ${userDetails.displayName}`);
      } else {
        console.log("Unable to fetch user details.");
      }

      // // Echo the message back
      // const replyText = `Echo: ${context.activity.text}`;
      // await context.sendActivity(replyText);

      const result = await askQuestionToBackend(
        context.activity.text,
        userDetails.mail
      );
      await context.sendActivity(result);

      await next();
    });

    // // Activity handler for message event.
    // this.onMessage(async (context, next) => {
    //   TurnContext.removeRecipientMention(context.activity);
    //   const replyText = `Echo: ${context.activity.text}`;
    //   await context.sendActivity(MessageFactory.text(replyText, replyText));
    // });

    // Activity handler for task module fetch event.
    this.handleTeamsTaskModuleFetch = async (context, taskModuleRequest) => {
      try {
        var meetingId = taskModuleRequest.data.meetingId;

        return {
          task: {
            type: "continue",
            value: {
              title: "Meeting Transcript",
              height: 600,
              width: 600,
              url: `${process.env.AppBaseUrl}/home?meetingId=${meetingId}`,
            },
          },
        };
      } catch (ex) {
        return {
          task: {
            type: "continue",
            value: {
              title: "Testing",
              height: 600,
              width: 600,
              url: `${process.env.AppBaseUrl}/home`,
            },
          },
        };
      }
    };

    // Activity handler for meeting end event.
    this.onTeamsMeetingEndEvent(async (meeting, context, next) => {
      var meetingDetails = await TeamsInfo.getMeetingInfo(context);
      var graphHelper = new GraphHelper();

      // Get the user's ID from the activity
      const userId = context.activity.from.aadObjectId; // Use 'aadObjectId' for Azure AD-based user ID

      // Fetch user details
      const userDetails = await graphHelper.GetUserDetailsAsync(userId);

      var result = await graphHelper.GetMeetingTranscriptionsAsync(
        meetingDetails.details.msGraphResourceId
      );
      if (result != "") {
        // Write the string to the file
        sendTranscriptToBackend(result, userDetails.mail);

        result = result.replace("<v", "");
        var foundIndex = transcriptsDictionary.findIndex(
          (x) => x.id === meetingDetails.details.msGraphResourceId
        );

        if (foundIndex != -1) {
          transcriptsDictionary[foundIndex].data = result;
        } else {
          transcriptsDictionary.push({
            id: meetingDetails.details.msGraphResourceId,
            data: result,
          });
        }

        var cardJson = {
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
          version: "1.5",
          type: "AdaptiveCard",
          body: [
            {
              type: "TextBlock",
              text: "Here is the last transcript details of the meeting.",
              weight: "Bolder",
              size: "Large",
            },
          ],
          actions: [
            {
              type: "Action.Submit",
              title: "View Transcript",
              data: {
                msteams: {
                  type: "task/fetch",
                },
                meetingId: meetingDetails.details.msGraphResourceId,
              },
            },
          ],
        };

        await context.sendActivity({
          attachments: [CardFactory.adaptiveCard(cardJson)],
        });
      } else {
        var notFoundCardJson = {
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
          version: "1.5",
          type: "AdaptiveCard",
          body: [
            {
              type: "TextBlock",
              // text: "No EncontradoxXx.",
              text: "Transcript not found for this meeting xD",
              weight: "Bolder",
              size: "Large",
            },
          ],
        };

        await context.sendActivity({
          attachments: [CardFactory.adaptiveCard(notFoundCardJson)],
        });
      }
    });
  }
}

// FXR DEFINED
function removeLinesWithArrow(input) {
  // Split the input string into lines
  const lines = input.split("\n");

  // Filter out lines that contain "-->"
  const filteredLines = lines.filter((line) => !line.includes("-->"));

  // Join the filtered lines back into a single string
  return filteredLines.join("\n");
}

// HAHAHAAHHAHA
// HAHAHAAHHAHA
// HAHAHAAHHAHA

async function askQuestionToBackend(prompt, email) {
  try {
    // Step 3: Send the POST request
    const response = await axios.get(
      `${process.env.API_URL}/prompt?query=${prompt}`,
      {
        headers: {
          email: email,
        },
      }
    );

    // console.log("Response from server:", response.data);
    return response.data.result;
  } catch (error) {
    console.error(
      "Error sending transcript to backend:",
      error.response?.data || error.message
    );
  }
}

async function sendTranscriptToBackend(transcript, email) {
  let cleanText = removeLinesWithArrow(transcript);

  // Step 1: Generate a PDF from cleanText
  const pdfBuffer = await generatePDF(cleanText);

  // Step 2: Prepare FormData
  const formData = new FormData();
  formData.append("files", pdfBuffer, { filename: "transcript.pdf" });

  try {
    // Step 3: Send the POST request
    const response = await axios.post(
      `${process.env.API_URL}/extract-text`,
      formData,
      {
        headers: {
          email: email,
          ...formData.getHeaders(),
        },
      }
    );

    console.log("Response from server:", response.data);
  } catch (error) {
    console.error(
      "Error sending transcript to backend:",
      error.response?.data || error.message
    );
  }
}

// Utility function to generate a PDF from text
function generatePDF(text) {
  return new Promise((resolve, reject) => {
    const doc = new PDFDocument();
    const buffers = [];

    doc.on("data", (chunk) => buffers.push(chunk));
    doc.on("end", () => resolve(Buffer.concat(buffers)));
    doc.on("error", reject);

    doc.text(text); // Add the clean text to the PDF
    doc.end();
  });
}
module.exports.ActivityBot = ActivityBot;
