// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "LFunctionLibrary.generated.h"

/**
 * 
 */
UCLASS()
class UE5PROJECT_API ULFunctionLibrary : public UObject
{
	GENERATED_BODY()
public:
	
	UFUNCTION(BlueprintCallable)
	static FString TimeStampAsString_Now();
	
	
};
