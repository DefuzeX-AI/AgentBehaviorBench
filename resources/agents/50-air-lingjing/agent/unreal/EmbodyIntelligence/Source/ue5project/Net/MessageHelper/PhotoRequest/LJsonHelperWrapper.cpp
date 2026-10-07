// Fill out your copyright notice in the Description page of Project Settings.


#include "LJsonHelperWrapper.h"

#include "LJsonHelper.h"

uint8 ULJsonHelperWrapper::GetCommandType(const FString& InMessage)
{
	return FLJsonHelper::GetCommandType(InMessage);
}

FString ULJsonHelperWrapper::GetCommandTypeAsString(const FString& InMessage)
{
	return FLJsonHelper::GetCommandTypeAsString(InMessage);
}

void ULJsonHelperWrapper::ParsePhotoRequest(const FString& InMessage, TArray<FLPhotoTask>& PhotoTasks)
{
	return FLJsonHelper::ParsePhotoRequest(InMessage, PhotoTasks);
}
