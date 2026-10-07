// Fill out your copyright notice in the Description page of Project Settings.

#include "ImageHelper.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"

AImageHelper::AImageHelper()
{
	PrimaryActorTick.bCanEverTick = false;

	const FString RandCharList = TEXT("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ");
	Boundary = TEXT("----HandsomeLaithLiu");
	for (int32 i = 0; i < 16; ++i)
	{
		Boundary += RandCharList[FMath::RandRange(0, RandCharList.Len() - 1)];
	}
}

FString AImageHelper::GetImageJson(const FString& ImageName)
{
	TArray<uint8> FileData;
	if (!FFileHelper::LoadFileToArray(FileData, *ImageName))
	{
		UE_LOG(LogTemp, Log, TEXT("\u52a0\u8f7d\u56fe\u7247Json\u5931\u8d25"));
		return FString();
	}

	const FString Base64String = FBase64::Encode(FileData);
	const FString JsonString = FString::Printf(
		TEXT("{\"commandType\": \"sendToEngine\", \"command\": {\"image\": \"%s\"}}"), *Base64String);

	return JsonString;
}

void AImageHelper::UploadImageWithJsonString(
	const FString& InUrl,
	const FString& InFileField,
	const FString& InFieldsJsonString,
	const FString& InFilePath,
	TFunction<void(bool bSucceed, const FString& ResponseMessage)> InCallback)
{
	TArray<uint8> FileContent;
	if (!FFileHelper::LoadFileToArray(FileContent, *InFilePath))
	{
		FString ErrorMsg = FString::Printf(TEXT("\u65e0\u6cd5\u8bfb\u53d6\u672c\u5730\u56fe\u7247\u6587\u4ef6: %s"), *InFilePath);
		UE_LOG(LogTemp, Error, TEXT("[Upload] %s"), *ErrorMsg);
		if (InCallback) InCallback(false, ErrorMsg);
		return;
	}

	TArray<uint8> BodyContent;
	auto AppendString = [&BodyContent](const FString& Str)
		{
			FTCHARToUTF8 UTF8String(*Str);
			BodyContent.Append((const uint8*)UTF8String.Get(), UTF8String.Length());
		};

	TSharedPtr<FJsonObject> JsonObject;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(InFieldsJsonString);

	if (FJsonSerializer::Deserialize(Reader, JsonObject) && JsonObject.IsValid())
	{
		for (const auto& Pair : JsonObject->Values)
		{
			FString ValueStr = TEXT("");

			if (Pair.Value->Type == EJson::String)
			{
				ValueStr = Pair.Value->AsString();
			}
			else if (Pair.Value->Type == EJson::Number)
			{
				ValueStr = FString::FromInt(FMath::RoundToInt(Pair.Value->AsNumber()));
			}
			else if (Pair.Value->Type == EJson::Boolean)
			{
				ValueStr = Pair.Value->AsBool() ? TEXT("true") : TEXT("false");
			}

			AppendString(FString::Printf(TEXT("--%s\r\n"), *Boundary));
			AppendString(FString::Printf(TEXT("Content-Disposition: form-data; name=\"%s\"\r\n\r\n"), *Pair.Key));
			AppendString(FString::Printf(TEXT("%s\r\n"), *ValueStr));
		}
	}
	else
	{
		FString JsonError = FString::Printf(TEXT("JSON \u5b57\u7b26\u4e32\u89e3\u6790\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u84dd\u56fe\u5185\u8f93\u5165\u7684\u6587\u672c\u683c\u5f0f: %s"), *InFieldsJsonString);
		UE_LOG(LogTemp, Error, TEXT("[Upload] %s"), *JsonError);
		if (InCallback) InCallback(false, JsonError);
		return;
	}

	const FString CleanFileName = FPaths::GetCleanFilename(InFilePath);
	const FString TargetFileField = InFileField.IsEmpty() ? TEXT("file") : InFileField;

	AppendString(FString::Printf(TEXT("--%s\r\n"), *Boundary));
	AppendString(FString::Printf(TEXT("Content-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"), *TargetFileField, *CleanFileName));
	AppendString(TEXT("Content-Type: image/png\r\n\r\n"));
	BodyContent.Append(FileContent);
	AppendString(TEXT("\r\n"));

	AppendString(FString::Printf(TEXT("--%s--\r\n"), *Boundary));

	FHttpModule::Get().SetHttpTimeout(600.0f);
	const TSharedPtr<IHttpRequest> Request = FHttpModule::Get().CreateRequest();
	Request->SetURL(InUrl);
	Request->SetVerb("POST");
	Request->SetTimeout(5000);
	Request->SetHeader(TEXT("Expect"), TEXT(""));
	Request->SetHeader(TEXT("Content-Type"), FString::Printf(TEXT("multipart/form-data; boundary=%s"), *Boundary));
	Request->SetContent(BodyContent);

	UE_LOG(LogTemp, Log, TEXT("[Upload] \u6b63\u5728\u53d1\u9001\u8bf7\u6c42\u81f3: %s"), *Request->GetURL());

	Request->OnProcessRequestComplete().BindLambda([InCallback](FHttpRequestPtr InRequest, FHttpResponsePtr InResponse, bool bConnectedSuccessfully)
		{
			bool bRealSuccess = false;
			FString Message = TEXT("");

			if (!InRequest.IsValid() || !bConnectedSuccessfully || !InResponse.IsValid())
			{
				Message = TEXT("\u7f51\u7edc\u8fde\u4e0d\u4e0a\u670d\u52a1\u5668\u6216\u54cd\u5e94\u65e0\u6548");
			}
			else
			{
				int32 ResponseCode = InResponse->GetResponseCode();
				FString ResponseContent = InResponse->GetContentAsString();

				if (EHttpResponseCodes::IsOk(ResponseCode))
				{
					bRealSuccess = true;
					Message = ResponseContent;
				}
				else
				{
					Message = FString::Printf(TEXT("\u670d\u52a1\u5668\u62a5\u9519(500\u6216\u5176\u4ed6)! \u8fd4\u56de\u5185\u5bb9: %s"), *ResponseContent);
				}
			}


			if (InCallback)
			{
				InCallback(bRealSuccess, Message);
			}
		});

	Request->ProcessRequest();
}

void AImageHelper::UploadBridgeTaskImage(
	const FString& InUrl,
	const FString& InFileField,
	const FString& InFieldsJsonString,
	const FString& InFilePath,
	bool& bOutSucceed,
	FString& OutMessage)
{


	bOutSucceed = false;
	OutMessage = TEXT("\u8bf7\u6c42\u5df2\u53d1\u9001\uff0c\u7b49\u5f85\u670d\u52a1\u5668\u5904\u7406\u4e2d...");


	UploadImageWithJsonString(InUrl, InFileField, InFieldsJsonString, InFilePath, [&bOutSucceed, &OutMessage](bool bSucceed, const FString& ResponseMessage)
		{
			bOutSucceed = bSucceed;
			OutMessage = ResponseMessage;


			if (GEngine)
			{
				FColor PrintColor = bSucceed ? FColor::Green : FColor::Red;
				GEngine->AddOnScreenDebugMessage(-1, 15.0f, PrintColor, FString::Printf(TEXT("\u3010\u540e\u7aef\u8fd4\u56de\u65e5\u5fd7\u3011: %s"), *ResponseMessage));
			}
		});
}