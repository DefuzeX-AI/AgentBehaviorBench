// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "LPhotoRequestStruct.h"
#include "UObject/Object.h"
#include "LJsonHelperWrapper.generated.h"

/**
 * 
 */
UCLASS()
class UE5PROJECT_API ULJsonHelperWrapper : public UObject
{
	GENERATED_BODY()
	
public:
	UFUNCTION(BlueprintCallable)
	static uint8 GetCommandType(const FString& InMessage);
	UFUNCTION(BlueprintCallable)
	static FString GetCommandTypeAsString(const FString& InMessage);
	UFUNCTION(BlueprintCallable)
	static void ParsePhotoRequest(const FString& InMessage, TArray<FLPhotoTask>& PhotoTasks);
	
	
};
