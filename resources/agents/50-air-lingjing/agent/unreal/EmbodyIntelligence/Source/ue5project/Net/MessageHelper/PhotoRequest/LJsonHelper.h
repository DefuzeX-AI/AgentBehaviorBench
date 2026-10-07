#pragma once

#include "CoreMinimal.h"
#include "LPhotoRequestStruct.h"

class UE5PROJECT_API FLJsonHelper
{
public:
	static FLJsonHelper* Get();

	// 1 TakePhoto, 2 ResetScenario
	static uint8 GetCommandType(const FString& InMessage);
	static FString GetCommandTypeAsString(const FString& InMessage);
	

	static uint8 GetRequestType(const FString& InMessage); 
	static void ParsePhotoRequest(const FString& InMessage, TArray<FLPhotoTask>& PhotoTasks);
	









};
