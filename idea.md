# Project: AI Two-Person Conversation Video Generator

## Role
Act as a senior full-stack developer, AI engineer, and UI/UX designer. Build a complete application that generates engaging two-person conversational videos from AI-generated ideas and user-provided character images.

The application should have a modular architecture so that additional video formats can be added in the future. The first supported format is a two-person conversation video.

## 1. Project Overview

Build an AI-powered video creation platform with this workflow:

1. Generate interesting ideas using an LLM API.
2. Select an idea and generate a high-quality conversational script between two characters.
3. Assign a different voice to each character.
4. Generate audio for both characters using a text-to-speech API.
5. Combine the character images and generated audio into a video.
6. Add synchronized subtitles.
7. Preview and export the final video.

The application should be designed so users can eventually add other video formats without rewriting the entire application.

## 2. AI Idea Generation

Integrate Groq API as the primary LLM provider, with support for other compatible providers such as OpenAI and locally hosted models where practical.

Allow users to:
- Generate multiple ideas at once.
- Specify a topic or generate ideas automatically.
- Choose the tone: educational, humorous, informative, philosophical, casual, or technical.
- Set the target video duration.
- Regenerate ideas.
- Save and manage ideas.
- Select an idea to proceed to script generation.

For technical topics, ideas should be engaging and suitable for a two-person conversation.

Store API keys securely on the backend using environment variables.

## 3. AI Script Generation

After selecting an idea, generate a natural, engaging, two-person dialogue.

Characters:
- Character A: A person standing normally with one hand in their pocket.
- Character B: A person standing in a thinking pose.

The user will supply two existing character images. Do not generate replacement character images by default.

Script requirements:
- A strong opening hook.
- Natural conversational language.
- Clear distinction between the two speakers.
- No robotic or repetitive dialogue.
- Interesting questions and informative answers.
- A logical flow and satisfying conclusion.
- Suitable pacing for the selected video duration.
- Short, voice-friendly sentences.
- Avoid unnecessarily long monologues.

The script editor should let users:
- Edit individual dialogue lines.
- Add, remove, and reorder dialogue.
- Regenerate the entire script or a particular line.
- Assign lines to either character.
- Preview the script before generating audio.

Represent the script as structured JSON, with each dialogue line containing a speaker, text, and optional delivery instructions.

Example:
{
  "title": "GPT-OSS vs GitHub Copilot",
  "dialogue": [
    {
      "speaker": "character_a",
      "text": "Have you ever wondered how open-source AI models compare with coding assistants?",
      "emotion": "curious"
    },
    {
      "speaker": "character_b",
      "text": "Absolutely! But first, we need to understand what makes them different.",
      "emotion": "thoughtful"
    }
  ]
}

Validate the generated output before sending it to the audio generation service.

## 4. Character Image Management

The user already has two character images.

Provide an image upload interface for:
- Character A: standing with one hand in their pocket.
- Character B: standing in a thinking pose.

Requirements:
- Support PNG, JPEG, and WebP.
- Preserve the original image quality.
- Display a preview of both images.
- Allow users to replace the images.
- Keep character positions consistent throughout the video.
- Use a white background or a user-configurable background.
- Do not distort the characters when resizing.

Initially, the characters should remain static. The generated video should simulate a conversation using the two images, audio, and subtitles. Keep the architecture open to future lip-sync or character animation.

## 5. AI Voice Generation (Deepgram)

Use Deepgram's text-to-speech API to generate the dialogue audio.

Research and select two suitable Deepgram voices for the characters. The two voices should be clearly distinguishable, natural, pleasant, and suitable for a conversational video.

Voice selection requirements:
- Character A should have a friendly, confident, conversational voice.
- Character B should have a thoughtful, expressive voice.
- Prefer voices with natural pronunciation and good intelligibility.
- Verify the current availability of the voices through official Deepgram documentation.

Do not hardcode voice names without verifying that they are supported.

Provide a voice configuration screen where users can:
- Select a voice for each character.
- Preview available voices using sample text.
- Adjust speaking speed and volume if supported.
- Regenerate audio for individual lines.
- Regenerate the complete dialogue audio.
- Listen to the generated audio before rendering.

Generate audio for each dialogue line separately so that users can regenerate individual lines without recreating the entire video.

Store audio files and their metadata for each script version.

Handle API errors, rate limits, and failed audio generation gracefully.

## 6. Audio Processing

Use FFmpeg for audio processing.

Requirements:
- Generate a separate audio file for each dialogue line.
- Normalize audio levels where appropriate.
- Add configurable pauses between speakers.
- Support optional background music.
- Allow the user to adjust the overall audio volume.
- Combine the dialogue into a single continuous audio track.
- Avoid abrupt cuts between lines.
- Preserve synchronization between audio and subtitles.

Use a suitable audio format such as WAV or AAC for intermediate and final outputs, depending on the processing requirements.

## 7. Video Generation Using FFmpeg

Use FFmpeg as the primary video rendering engine.

The initial video format should show both character images side by side on a clean white background.

Layout:
- Character A on the left.
- Character B on the right.
- Both characters should remain visible throughout the video.
- Use a consistent aspect ratio and position.
- Ensure that images are properly scaled without stretching.
- Use a clean, minimal visual design.

The video should support:
- 9:16 vertical format for Instagram Reels, YouTube Shorts, and similar platforms.
- 16:9 horizontal format for YouTube.
- 1:1 square format as an optional output.

Use FFmpeg to:
1. Create the video canvas.
2. Place the two character images.
3. Add the generated dialogue audio.
4. Add synchronized subtitles.
5. Render the final video.
6. Export it in MP4 format using H.264 video and AAC audio.

The rendering pipeline should be modular and support future animation features.

For the initial version, static images are sufficient. Do not introduce unnecessary AI video-generation costs.

## 8. Subtitle Generation

Generate subtitles directly from the final dialogue script and its audio timings.

Subtitle requirements:
- White text.
- Black background behind the text.
- High readability.
- Centered near the bottom of the video.
- Proper line breaks.
- No subtitles overlapping the characters' faces.
- Display the current speaker's dialogue at the correct time.
- Support two-line subtitles when necessary.

Use the dialogue timing information to synchronize subtitles accurately.

Provide settings for:
- Font size.
- Subtitle position.
- Background opacity.
- Maximum characters per line.
- Subtitle margins.

Use FFmpeg subtitle filters or generate an SRT/ASS subtitle file and burn it into the final video.

## 9. Video Preview and Export

After rendering, provide:
- An embedded video player.
- Play and pause controls.
- A timeline or progress indicator.
- Audio playback.
- Subtitle preview.
- A button to regenerate the video.
- A download button for the final MP4.
- An option to download the audio separately.
- An option to download the subtitle file.

Allow users to return to the script editor and make changes before rendering again.

## 10. User Interface

Create a clean, modern, responsive interface.

Suggested workflow:

Step 1: Ideas
- Enter a topic or generate ideas automatically.
- Select an idea.

Step 2: Script
- Generate the two-person conversation.
- Edit and approve the dialogue.

Step 3: Characters
- Upload or select the two character images.
- Preview the layout.

Step 4: Voices
- Choose voices for each character.
- Preview and generate audio.

Step 5: Subtitles
- Configure subtitle appearance.
- Preview the subtitle style.

Step 6: Render
- Choose video dimensions and aspect ratio.
- Start video rendering.
- Show rendering progress and errors.

Step 7: Export
- Preview the completed video.
- Download the video, audio, and subtitles.

Use a step-based interface with a clear progress indicator. Users should be able to return to previous steps without losing their work.

## 11. Suggested Technology Stack

Frontend:
- Next.js
- React
- TypeScript
- Tailwind CSS

Backend:
- Next.js API routes or a separate Node.js and Express backend.
- TypeScript.

AI:
- Groq API for idea and script generation.
- An abstraction layer for supporting additional LLM providers.

Voice:
- Deepgram Text-to-Speech API.

Video:
- FFmpeg and FFprobe.

Database:
- PostgreSQL or Supabase.

Storage:
- Local storage during development.
- S3-compatible object storage or Supabase Storage for production.

Background processing:
- A job queue for script audio generation and video rendering.
- Redis and BullMQ are suitable options if required.

## 12. Application Architecture

Separate the application into the following modules:

- Idea Generation Service
- Script Generation Service
- Script Editor
- Character Image Manager
- Voice Management Service
- Text-to-Speech Service
- Audio Processing Service
- Subtitle Generation Service
- Video Rendering Service
- Export and Download Service
- Project Management Service

Use clear interfaces between modules so that the LLM provider, TTS provider, or rendering engine can be replaced independently.

The video rendering process should run as a background job rather than blocking the frontend request.

Maintain job statuses such as:
- Pending
- Generating Script
- Generating Audio
- Preparing Subtitles
- Rendering Video
- Completed
- Failed

Provide useful error messages and allow failed jobs to be retried.

## 13. Data Model

Create a database schema for:
- Users (if authentication is implemented).
- Projects.
- Ideas.
- Scripts.
- Dialogue lines.
- Character images.
- Voice configurations.
- Generated audio files.
- Subtitle configurations.
- Rendering jobs.
- Exported videos.

Each project should preserve its settings and generated assets.

Support multiple script versions and allow the user to return to earlier versions.

## 14. Security and Reliability

- Never expose API keys to the frontend.
- Validate uploaded images and file sizes.
- Validate AI-generated JSON before processing.
- Use safe file paths and prevent command injection when invoking FFmpeg.
- Clean up temporary files when they are no longer needed.
- Implement request timeouts and retries for external APIs.
- Provide meaningful error messages.
- Avoid losing project data if rendering fails.
- Keep long-running rendering jobs separate from normal API requests.

## 15. Future Features

Design the architecture to support:
- Additional video formats.
- Multiple character layouts.
- Animated character movements.
- AI lip-sync.
- Automatic background music.
- Multiple languages.
- Automatic translation and dubbing.
- More TTS providers.
- More LLM providers.
- Video templates.
- Batch video generation.
- Custom backgrounds.
- Automatic social-media aspect ratio conversion.

These are future features and should not delay the initial working version.

## 16. Development Instructions

Before writing code:
1. Study the official Groq API documentation.
2. Study the official Deepgram TTS documentation and currently available voices.
3. Check FFmpeg capabilities for image sequences, audio mixing, subtitle rendering, and video encoding.
4. Design the application architecture.
5. Define the data models and API interfaces.
6. Create an implementation plan.

Then implement the application incrementally.

Start with a working end-to-end MVP:
- Generate an idea.
- Generate a two-person script.
- Upload two character images.
- Generate speech using two different voices.
- Combine the images, audio, and subtitles.
- Render and preview a vertical MP4 video.

Do not build only a UI mockup. Implement the actual API integrations and rendering pipeline.

Write clean, modular, maintainable code with proper error handling and documentation. Include a README with setup instructions, environment variables, dependencies, and commands for running the application locally.

At the end, provide:
- A summary of the implemented features.
- The project directory structure.
- Installation and configuration instructions.
- Instructions for generating the first video.
- Any limitations or features that remain incomplete.

Prioritize a reliable, working end-to-end video generation pipeline over unnecessary features.